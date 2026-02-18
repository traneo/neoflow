"""Index curated GitLab repositories into Weaviate for hybrid search."""

import logging
import os
import re
import tempfile
import zipfile

import yaml
import weaviate
from weaviate.classes.config import Configure, DataType, Property
from weaviate.config import AdditionalConfig, Timeout

from neoflow.config import Config, GitLabConfig
from neoflow.gitlab.api import GitLabClient

logger = logging.getLogger(__name__)

OVERLAP_LINES = 2

# --- Code-only filtering for zip imports ---

CODE_EXTENSIONS = frozenset({
    # Python
    ".py", ".pyx", ".pxd",
    # JavaScript / TypeScript
    ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
    # JVM
    ".java", ".kt", ".kts", ".scala", ".groovy",
    # Go
    ".go",
    # Rust
    ".rs",
    # C / C++
    ".c", ".h", ".cpp", ".hpp", ".cc", ".hh", ".cxx",
    # C#
    ".cs",
    # Ruby
    ".rb",
    # Swift
    ".swift",
    # SQL
    ".sql",
    # Shell
    ".sh", ".bash", ".zsh",
    # PHP
    ".php",
    # Dart
    ".dart",
    # Lua
    ".lua",
    # R
    ".r", ".R",
})

SKIP_DIRS = frozenset({
    "node_modules", "vendor", ".git", "__pycache__", ".venv", "venv",
    "dist", "build", ".tox", ".mypy_cache", ".pytest_cache",
    ".eggs", "egg-info", ".gradle", ".idea", ".vscode",
    "target", "bin", "obj", ".next", ".nuxt", "coverage",
})

SKIP_FILES = frozenset({
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "Pipfile.lock", "poetry.lock", "composer.lock",
    "Gemfile.lock", "go.sum", "Cargo.lock",
    "LICENSE", "LICENSE.md", "LICENSE.txt",
    "CHANGELOG", "CHANGELOG.md",
})

SKIP_FILE_PATTERNS = [
    re.compile(r"\.min\.(js|css)$"),
    re.compile(r"\.bundle\.(js|css)$"),
    re.compile(r"\.generated\.\w+$"),
    re.compile(r"\.d\.ts$"),
]

# Regex patterns for extracting imports (language-agnostic, covers common cases)
_IMPORT_PATTERNS = [
    re.compile(r"^\s*import\s+(.+)", re.MULTILINE),               # Python, Java, JS/TS, Go
    re.compile(r"^\s*from\s+(\S+)\s+import", re.MULTILINE),       # Python from-imports
    re.compile(r"^\s*require\s*\(\s*['\"](.+?)['\"]\s*\)", re.MULTILINE),  # Node require()
    re.compile(r"^\s*#include\s+[<\"](.+?)[>\"]", re.MULTILINE),  # C/C++
    re.compile(r"^\s*using\s+([\w.]+)\s*;", re.MULTILINE),        # C#
]

# Regex patterns for extracting definitions
_DEFINITION_PATTERNS = [
    re.compile(r"^\s*(?:export\s+)?(?:abstract\s+)?class\s+(\w+)", re.MULTILINE),
    re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)", re.MULTILINE),
    re.compile(r"^\s*def\s+(\w+)\s*\(", re.MULTILINE),           # Python
    re.compile(r"^\s*func\s+(\w+)\s*\(", re.MULTILINE),          # Go
    re.compile(r"^\s*(?:export\s+)?interface\s+(\w+)", re.MULTILINE),
    re.compile(r"^\s*(?:export\s+)?type\s+(\w+)\s*=", re.MULTILINE),  # TS type alias
    re.compile(r"^\s*struct\s+(\w+)", re.MULTILINE),              # Go, Rust, C
    re.compile(r"^\s*enum\s+(\w+)", re.MULTILINE),
]

_TEST_INDICATORS = re.compile(
    r"(^|/)tests?/|_test\.\w+$|\.test\.\w+$|\.spec\.\w+$|test_\w+\.py$",
)


def _is_code_file(file_path: str) -> bool:
    """Check if a file is a code file based on extension, name, and path."""
    basename = os.path.basename(file_path)

    if basename in SKIP_FILES:
        return False

    if any(p.search(basename) for p in SKIP_FILE_PATTERNS):
        return False

    _, ext = os.path.splitext(basename)
    return ext.lower() in CODE_EXTENSIONS


def _should_skip_dir(dirname: str) -> bool:
    """Check if a directory should be skipped entirely."""
    return dirname in SKIP_DIRS or dirname.endswith(".egg-info")


def _is_test_file(file_path: str) -> bool:
    """Detect if a file is a test file based on path and naming conventions."""
    return bool(_TEST_INDICATORS.search(file_path))


def _extract_imports(content: str) -> list[str]:
    """Extract import/include statements from source code."""
    imports = []
    for pattern in _IMPORT_PATTERNS:
        for match in pattern.finditer(content):
            imp = match.group(1).strip().rstrip(";")
            if imp and len(imp) < 200:
                imports.append(imp)
    return imports


def _extract_definitions(content: str) -> list[str]:
    """Extract class, function, struct, interface, and type names from source code."""
    definitions = []
    for pattern in _DEFINITION_PATTERNS:
        for match in pattern.finditer(content):
            name = match.group(1)
            if name and name not in definitions:
                definitions.append(name)
    return definitions


def _compute_line_ranges(content: str, chunks: list[str]) -> list[tuple[int, int]]:
    """Compute (line_start, line_end) for each chunk within the full file content.

    Line numbers are 1-based.
    """
    ranges = []
    search_from = 0
    for chunk in chunks:
        start_idx = content.find(chunk[:80], search_from)
        if start_idx == -1:
            start_idx = search_from

        line_start = content[:start_idx].count("\n") + 1
        line_end = line_start + chunk.count("\n")
        ranges.append((line_start, line_end))
        search_from = start_idx + len(chunk) // 2  # advance past overlap
    return ranges


# Patterns that indicate function/class boundaries for chunking
BOUNDARY_PATTERNS = [
    re.compile(r"^(class |def |function |async function |export |public |private |protected )"),
    re.compile(r"^(func |type |struct |interface )"),  # Go
    re.compile(r"^(package |import )"),
]


def load_repos_config(path: str) -> dict:
    """Parse the YAML repos configuration file."""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _create_code_snippets_collection(client, config: Config):
    """Create the CodeSnippets collection in Weaviate.

    Only ``content`` and ``definitions`` are vectorized. All other text
    properties (file_path, imports, etc.) are stored for filtering and
    display but skipped during vectorization to stay within the embedding
    model's context window.
    """
    name = "CodeSnippets"
    if client.collections.exists(name):
        client.collections.delete(name)
        logger.info("Deleted existing collection: %s", name)

    client.collections.create(
        name=name,
        description="Code snippets from curated repositories",
        vector_config=config.get_weaviate_vector_config(),
        properties=[
            # --- Vectorized (used for semantic search) ---
            Property(name="content", data_type=DataType.TEXT),
            Property(name="definitions", data_type=DataType.TEXT),
            # --- Not vectorized (metadata for filtering / display) ---
            Property(name="repository", data_type=DataType.TEXT, skip_vectorization=True),
            Property(name="file_path", data_type=DataType.TEXT, skip_vectorization=True),
            Property(name="file_name", data_type=DataType.TEXT, skip_vectorization=True),
            Property(name="directory", data_type=DataType.TEXT, skip_vectorization=True),
            Property(name="language", data_type=DataType.TEXT, skip_vectorization=True),
            Property(name="imports", data_type=DataType.TEXT, skip_vectorization=True),
            Property(name="url", data_type=DataType.TEXT, skip_vectorization=True),
            Property(name="is_test", data_type=DataType.BOOL, skip_vectorization=True),
            Property(name="is_readme", data_type=DataType.BOOL, skip_vectorization=True),
            Property(name="chunk_index", data_type=DataType.INT, skip_vectorization=True),
            Property(name="total_chunks", data_type=DataType.INT, skip_vectorization=True),
            Property(name="line_start", data_type=DataType.INT, skip_vectorization=True),
            Property(name="line_end", data_type=DataType.INT, skip_vectorization=True),
        ],
    )
    logger.info("Created CodeSnippets collection")


def _detect_language(file_path: str) -> str:
    """Detect programming language from file extension."""
    ext_map = {
        ".py": "python", ".pyx": "cython", ".pxd": "cython",
        ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript",
        ".ts": "typescript", ".tsx": "typescript",
        ".java": "java", ".kt": "kotlin", ".kts": "kotlin",
        ".scala": "scala", ".groovy": "groovy",
        ".go": "go",
        ".rs": "rust",
        ".c": "c", ".h": "c", ".cpp": "cpp", ".hpp": "cpp", ".cc": "cpp", ".hh": "cpp", ".cxx": "cpp",
        ".cs": "csharp",
        ".rb": "ruby",
        ".swift": "swift",
        ".sql": "sql",
        ".sh": "shell", ".bash": "shell", ".zsh": "shell",
        ".php": "php",
        ".dart": "dart",
        ".lua": "lua",
        ".r": "r", ".R": "r",
        ".md": "markdown",
        ".yaml": "yaml", ".yml": "yaml",
        ".json": "json", ".xml": "xml",
    }
    _, ext = os.path.splitext(file_path)
    return ext_map.get(ext, ext.lstrip("."))


def _is_boundary_line(line: str) -> bool:
    """Check if a line marks a function/class boundary."""
    stripped = line.lstrip()
    return any(p.match(stripped) for p in BOUNDARY_PATTERNS)


def _truncate_chunk(chunk: str, max_bytes: int) -> str:
    """Hard-truncate a chunk to max_bytes to stay within the embedding context."""
    encoded = chunk.encode("utf-8", errors="replace")
    if len(encoded) <= max_bytes:
        return chunk
    logger.debug("Truncating chunk from %d to %d bytes", len(encoded), max_bytes)
    return encoded[:max_bytes].decode("utf-8", errors="ignore")


def _chunk_content(content: str, chunk_size_bytes: int) -> list[str]:
    """Split large files by function/class boundaries with overlap.

    Files under chunk_size_bytes are returned as a single chunk.
    Every chunk is hard-capped at chunk_size_bytes to prevent embedding errors.
    """
    if len(content.encode("utf-8", errors="replace")) <= chunk_size_bytes:
        return [content]

    lines = content.splitlines(keepends=True)
    chunks: list[str] = []
    current_chunk_lines: list[str] = []
    current_size = 0

    for line in lines:
        line_size = len(line.encode("utf-8", errors="replace"))

        # Split at boundary lines OR when chunk exceeds size limit
        if current_chunk_lines and (
            _is_boundary_line(line)
            or current_size + line_size > chunk_size_bytes
        ):
            chunk_text = "".join(current_chunk_lines)
            chunks.append(chunk_text)
            # Start new chunk with overlap from end of previous
            overlap_start = max(0, len(current_chunk_lines) - OVERLAP_LINES)
            overlap_lines = current_chunk_lines[overlap_start:]
            current_chunk_lines = overlap_lines
            current_size = sum(len(l.encode("utf-8", errors="replace")) for l in overlap_lines)

        current_chunk_lines.append(line)
        current_size += line_size

    # Don't forget the last chunk
    if current_chunk_lines:
        chunks.append("".join(current_chunk_lines))

    result = chunks if chunks else [content]
    return [_truncate_chunk(c, chunk_size_bytes) for c in result]


def index_repository(repo: dict, gitlab_client: GitLabClient, weaviate_client, config: Config):
    """Fetch a repository's file tree, download content, and insert into Weaviate."""
    project_id = repo["project_id"]
    ref = repo.get("ref", "main")
    repo_name = repo.get("name", str(project_id))
    paths = repo.get("paths", [])

    logger.info("Indexing repository: %s (project %s, ref %s)", repo_name, project_id, ref)

    # Get file tree (for specific paths or full repo)
    tree_items = []
    if paths:
        for path in paths:
            tree_items.extend(gitlab_client.get_file_tree(project_id, ref=ref, path=path))
    else:
        tree_items.extend(gitlab_client.get_file_tree(project_id, ref=ref))

    # Filter to allowed file types
    allowed = config.gitlab.allowed_extensions
    files = [
        item for item in tree_items
        if item.get("type") == "blob"
        and any(item["path"].endswith(ext) for ext in allowed)
    ]
    logger.info("Found %d indexable files in %s", len(files), repo_name)

    collection = weaviate_client.collections.use("CodeSnippets")
    web_base = config.gitlab.base_url.replace("/api/v4", "")
    indexed = 0
    skipped = 0

    for file_item in files:
        file_path = file_item["path"]
        try:
            content = gitlab_client.get_file_content(project_id, file_path, ref=ref)
        except Exception as e:
            logger.warning("Failed to fetch %s: %s", file_path, e)
            skipped += 1
            continue

        # Skip files exceeding size limit
        if len(content.encode("utf-8", errors="replace")) > config.gitlab.max_file_size_bytes:
            logger.debug("Skipping oversized file: %s", file_path)
            skipped += 1
            continue

        language = _detect_language(file_path)
        is_readme = os.path.basename(file_path).lower().startswith("readme")
        url = f"{web_base}/{project_id}/-/blob/{ref}/{file_path}"

        chunks = _chunk_content(content, config.llm_provider.chunk_size_bytes)
        for chunk in chunks:
            try:
                collection.data.insert(
                    properties={
                        "repository": repo_name,
                        "file_path": file_path,
                        "content": chunk,
                        "language": language,
                        "is_readme": is_readme,
                        "url": url,
                    }
                )
                indexed += 1
            except Exception as e:
                logger.warning("Failed to index chunk of %s: %s", file_path, e)
                skipped += 1

    logger.info(
        "Repository %s: indexed %d chunks, %d skipped",
        repo_name, indexed, skipped,
    )


def _connect_weaviate(config: Config):
    """Create a Weaviate client connection."""
    wv = config.weaviate
    return weaviate.connect_to_local(
        additional_config=AdditionalConfig(
            timeout=Timeout(
                init=wv.timeout_init,
                query=wv.timeout_query,
                insert=wv.timeout_insert,
            )
        )
    )


def index_all_repos(config: Config):
    """Main entry point: load config and index all configured repositories."""
    repos_config = load_repos_config(config.gitlab.repos_config_path)
    repositories = repos_config.get("repositories", [])

    if not repositories:
        logger.warning("No repositories configured in %s", config.gitlab.repos_config_path)
        return

    logger.info("Indexing %d repositories...", len(repositories))

    with _connect_weaviate(config) as weaviate_client:
        _create_code_snippets_collection(weaviate_client, config)

        with GitLabClient(config.gitlab) as gitlab_client:
            for repo in repositories:
                try:
                    index_repository(repo, gitlab_client, weaviate_client, config)
                except Exception as e:
                    logger.error("Failed to index %s: %s", repo.get("name", repo.get("project_id")), e)

    logger.info("Indexing complete")


def refresh_repo(repo_name: str | None, config: Config):
    """Re-index one specific repository or all repositories.

    Args:
        repo_name: Name of repo to refresh, or None for all.
    """
    repos_config = load_repos_config(config.gitlab.repos_config_path)
    repositories = repos_config.get("repositories", [])

    if repo_name:
        repositories = [r for r in repositories if r.get("name") == repo_name]
        if not repositories:
            logger.error("Repository '%s' not found in config", repo_name)
            return

    with _connect_weaviate(config) as weaviate_client:
        # For refresh, recreate the collection to clear old data
        _create_code_snippets_collection(weaviate_client, config)

        with GitLabClient(config.gitlab) as gitlab_client:
            for repo in repositories:
                try:
                    index_repository(repo, gitlab_client, weaviate_client, config)
                except Exception as e:
                    logger.error("Failed to refresh %s: %s", repo.get("name"), e)

    logger.info("Refresh complete")


def _ensure_code_snippets_collection(client, config: Config):
    """Create CodeSnippets collection only if it doesn't already exist."""
    if not client.collections.exists("CodeSnippets"):
        _create_code_snippets_collection(client, config)


def index_zip_file(zip_path: str, repo_name: str, config: Config):
    """Extract a zip archive and index its code files into Weaviate.

    Only indexes source code files (see CODE_EXTENSIONS). Documentation,
    config, lock files, vendored dependencies, and build artifacts are skipped.

    Each chunk is enriched with metadata: file_name, directory, chunk_index,
    total_chunks, line_start, line_end, is_test, imports, and definitions.

    Operates in append mode — existing CodeSnippets data is preserved.
    """
    if not zipfile.is_zipfile(zip_path):
        raise ValueError(f"Not a valid zip file: {zip_path}")

    max_size = config.gitlab.max_file_size_bytes

    with tempfile.TemporaryDirectory() as tmp_dir:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(tmp_dir)

        # Find the common root (zip archives often have a single top-level dir)
        entries = os.listdir(tmp_dir)
        if len(entries) == 1 and os.path.isdir(os.path.join(tmp_dir, entries[0])):
            root = os.path.join(tmp_dir, entries[0])
        else:
            root = tmp_dir

        # Collect code files, skipping non-code and noisy directories
        files: list[str] = []
        for dirpath, dirnames, filenames in os.walk(root):
            # Prune directories we never want to descend into
            dirnames[:] = [d for d in dirnames if not _should_skip_dir(d)]

            for fname in filenames:
                rel = os.path.relpath(os.path.join(dirpath, fname), root)
                if _is_code_file(rel):
                    files.append(os.path.join(dirpath, fname))

        logger.info("Found %d code files in %s", len(files), zip_path)

        with _connect_weaviate(config) as weaviate_client:
            _ensure_code_snippets_collection(weaviate_client, config)
            collection = weaviate_client.collections.use("CodeSnippets")

            indexed = 0
            skipped = 0

            for full_path in files:
                rel_path = os.path.relpath(full_path, root)

                try:
                    with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
                except Exception as e:
                    logger.warning("Failed to read %s: %s", rel_path, e)
                    skipped += 1
                    continue

                if len(content.encode("utf-8", errors="replace")) > max_size:
                    logger.debug("Skipping oversized file: %s", rel_path)
                    skipped += 1
                    continue

                language = _detect_language(rel_path)
                is_test = _is_test_file(rel_path)
                file_name = os.path.basename(rel_path)
                directory = os.path.dirname(rel_path) or "."

                # Extract file-level metadata
                imports = _extract_imports(content)
                definitions = _extract_definitions(content)

                chunks = _chunk_content(content, config.llm_provider.chunk_size_bytes)
                total_chunks = len(chunks)
                line_ranges = _compute_line_ranges(content, chunks)

                for chunk_idx, chunk in enumerate(chunks):
                    line_start, line_end = line_ranges[chunk_idx]
                    # Extract chunk-level definitions (more precise than file-level)
                    chunk_definitions = _extract_definitions(chunk)

                    try:
                        collection.data.insert(
                            properties={
                                "repository": repo_name,
                                "file_path": rel_path,
                                "file_name": file_name,
                                "directory": directory,
                                "content": chunk,
                                "language": language,
                                "is_test": is_test,
                                "chunk_index": chunk_idx,
                                "total_chunks": total_chunks,
                                "line_start": line_start,
                                "line_end": line_end,
                                "imports": "\n".join(imports) if imports else "",
                                "definitions": ", ".join(chunk_definitions) if chunk_definitions else "",
                            }
                        )
                        indexed += 1
                    except Exception as e:
                        logger.warning(
                            "Failed to index chunk %d/%d of %s: %s",
                            chunk_idx + 1, total_chunks, rel_path, e,
                        )
                        skipped += 1

    logger.info(
        "Zip import %s: indexed %d chunks, %d skipped",
        repo_name, indexed, skipped,
    )
