"""Index code snippets from local zip archives into Weaviate."""

import logging
import os
import re
import tempfile
import zipfile

import weaviate
from weaviate.classes.config import DataType, Property
from weaviate.config import AdditionalConfig, Timeout

from neoflow.config import Config

logger = logging.getLogger(__name__)

OVERLAP_LINES = 2

CODE_EXTENSIONS = frozenset({
    ".py", ".pyx", ".pxd",
    ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
    ".java", ".kt", ".kts", ".scala", ".groovy",
    ".go",
    ".rs",
    ".c", ".h", ".cpp", ".hpp", ".cc", ".hh", ".cxx",
    ".cs",
    ".rb",
    ".swift",
    ".sql",
    ".sh", ".bash", ".zsh",
    ".php",
    ".dart",
    ".lua",
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

_IMPORT_PATTERNS = [
    re.compile(r"^\s*import\s+(.+)", re.MULTILINE),
    re.compile(r"^\s*from\s+(\S+)\s+import", re.MULTILINE),
    re.compile(r"^\s*require\s*\(\s*['\"](.+?)['\"]\s*\)", re.MULTILINE),
    re.compile(r"^\s*#include\s+[<\"](.+?)[>\"]", re.MULTILINE),
    re.compile(r"^\s*using\s+([\w.]+)\s*;", re.MULTILINE),
]

_DEFINITION_PATTERNS = [
    re.compile(r"^\s*(?:export\s+)?(?:abstract\s+)?class\s+(\w+)", re.MULTILINE),
    re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)", re.MULTILINE),
    re.compile(r"^\s*def\s+(\w+)\s*\(", re.MULTILINE),
    re.compile(r"^\s*func\s+(\w+)\s*\(", re.MULTILINE),
    re.compile(r"^\s*(?:export\s+)?interface\s+(\w+)", re.MULTILINE),
    re.compile(r"^\s*(?:export\s+)?type\s+(\w+)\s*=", re.MULTILINE),
    re.compile(r"^\s*struct\s+(\w+)", re.MULTILINE),
    re.compile(r"^\s*enum\s+(\w+)", re.MULTILINE),
]

_TEST_INDICATORS = re.compile(
    r"(^|/)tests?/|_test\.\w+$|\.test\.\w+$|\.spec\.\w+$|test_\w+\.py$",
)

BOUNDARY_PATTERNS = [
    re.compile(r"^(class |def |function |async function |export |public |private |protected )"),
    re.compile(r"^(func |type |struct |interface )"),
    re.compile(r"^(package |import )"),
]


def _is_code_file(file_path: str) -> bool:
    basename = os.path.basename(file_path)

    if basename in SKIP_FILES:
        return False

    if any(pattern.search(basename) for pattern in SKIP_FILE_PATTERNS):
        return False

    _, ext = os.path.splitext(basename)
    return ext.lower() in CODE_EXTENSIONS


def _should_skip_dir(dirname: str) -> bool:
    return dirname in SKIP_DIRS or dirname.endswith(".egg-info")


def _is_test_file(file_path: str) -> bool:
    return bool(_TEST_INDICATORS.search(file_path))


def _extract_imports(content: str) -> list[str]:
    imports = []
    for pattern in _IMPORT_PATTERNS:
        for match in pattern.finditer(content):
            imp = match.group(1).strip().rstrip(";")
            if imp and len(imp) < 200:
                imports.append(imp)
    return imports


def _extract_definitions(content: str) -> list[str]:
    definitions = []
    for pattern in _DEFINITION_PATTERNS:
        for match in pattern.finditer(content):
            name = match.group(1)
            if name and name not in definitions:
                definitions.append(name)
    return definitions


def _compute_line_ranges(content: str, chunks: list[str]) -> list[tuple[int, int]]:
    ranges = []
    search_from = 0
    for chunk in chunks:
        start_idx = content.find(chunk[:80], search_from)
        if start_idx == -1:
            start_idx = search_from

        line_start = content[:start_idx].count("\n") + 1
        line_end = line_start + chunk.count("\n")
        ranges.append((line_start, line_end))
        search_from = start_idx + len(chunk) // 2
    return ranges


def _detect_language(file_path: str) -> str:
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
    stripped = line.lstrip()
    return any(pattern.match(stripped) for pattern in BOUNDARY_PATTERNS)


def _truncate_chunk(chunk: str, max_bytes: int) -> str:
    encoded = chunk.encode("utf-8", errors="replace")
    if len(encoded) <= max_bytes:
        return chunk
    logger.debug("Truncating chunk from %d to %d bytes", len(encoded), max_bytes)
    return encoded[:max_bytes].decode("utf-8", errors="ignore")


def chunk_content(content: str, chunk_size_bytes: int) -> list[str]:
    if len(content.encode("utf-8", errors="replace")) <= chunk_size_bytes:
        return [content]

    lines = content.splitlines(keepends=True)
    chunks: list[str] = []
    current_chunk_lines: list[str] = []
    current_size = 0

    for line in lines:
        line_size = len(line.encode("utf-8", errors="replace"))

        if current_chunk_lines and (
            _is_boundary_line(line)
            or current_size + line_size > chunk_size_bytes
        ):
            chunk_text = "".join(current_chunk_lines)
            chunks.append(chunk_text)
            overlap_start = max(0, len(current_chunk_lines) - OVERLAP_LINES)
            overlap_lines = current_chunk_lines[overlap_start:]
            current_chunk_lines = overlap_lines
            current_size = sum(len(part.encode("utf-8", errors="replace")) for part in overlap_lines)

        current_chunk_lines.append(line)
        current_size += line_size

    if current_chunk_lines:
        chunks.append("".join(current_chunk_lines))

    result = chunks if chunks else [content]
    return [_truncate_chunk(chunk, chunk_size_bytes) for chunk in result]


def _connect_weaviate(config: Config):
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


def _create_code_snippets_collection(client, config: Config):
    name = "CodeSnippets"
    if client.collections.exists(name):
        client.collections.delete(name)
        logger.info("Deleted existing collection: %s", name)

    client.collections.create(
        name=name,
        description="Code snippets from imported repositories",
        vector_config=config.get_weaviate_vector_config(),
        properties=[
            Property(name="content", data_type=DataType.TEXT),
            Property(name="definitions", data_type=DataType.TEXT),
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


def _ensure_code_snippets_collection(client, config: Config):
    if not client.collections.exists("CodeSnippets"):
        _create_code_snippets_collection(client, config)


def _collect_code_files(root: str) -> list[str]:
    files: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [dirname for dirname in dirnames if not _should_skip_dir(dirname)]

        for filename in filenames:
            rel_path = os.path.relpath(os.path.join(dirpath, filename), root)
            if _is_code_file(rel_path):
                files.append(os.path.join(dirpath, filename))
    return files


def _index_code_from_root(root: str, repo_name: str, source_label: str, config: Config):
    max_size = config.importer.max_file_size_bytes
    files = _collect_code_files(root)

    logger.info("Found %d code files in %s", len(files), source_label)

    with _connect_weaviate(config) as weaviate_client:
        _ensure_code_snippets_collection(weaviate_client, config)
        collection = weaviate_client.collections.use("CodeSnippets")

        indexed = 0
        skipped = 0

        for full_path in files:
            rel_path = os.path.relpath(full_path, root)

            try:
                with open(full_path, "r", encoding="utf-8", errors="replace") as file:
                    content = file.read()
            except Exception as exc:
                logger.warning("Failed to read %s: %s", rel_path, exc)
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
            imports = _extract_imports(content)
            definitions = _extract_definitions(content)

            chunks = chunk_content(content, config.llm_provider.chunk_size_bytes)
            total_chunks = len(chunks)
            line_ranges = _compute_line_ranges(content, chunks)

            for chunk_idx, chunk in enumerate(chunks):
                line_start, line_end = line_ranges[chunk_idx]
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
                except Exception as exc:
                    logger.warning(
                        "Failed to index chunk %d/%d of %s: %s",
                        chunk_idx + 1,
                        total_chunks,
                        rel_path,
                        exc,
                    )
                    skipped += 1

    logger.info(
        "Code import %s from %s: indexed %d chunks, %d skipped",
        repo_name,
        source_label,
        indexed,
        skipped,
    )


def index_zip_file(zip_path: str, repo_name: str, config: Config):
    if not zipfile.is_zipfile(zip_path):
        raise ValueError(f"Not a valid zip file: {zip_path}")

    MAX_UNCOMPRESSED = 500 * 1024 * 1024  # 500 MB total

    with tempfile.TemporaryDirectory() as tmp_dir:
        with zipfile.ZipFile(zip_path, "r") as archive:
            total_size = 0
            for member in archive.infolist():
                if member.filename.startswith('/') or '..' in member.filename:
                    raise ValueError(f"Unsafe path in zip: {member.filename}")
                total_size += member.file_size
                if total_size > MAX_UNCOMPRESSED:
                    raise ValueError("Zip file exceeds maximum uncompressed size (500 MB)")
            archive.extractall(tmp_dir)

        entries = os.listdir(tmp_dir)
        if len(entries) == 1 and os.path.isdir(os.path.join(tmp_dir, entries[0])):
            root = os.path.join(tmp_dir, entries[0])
        else:
            root = tmp_dir

        _index_code_from_root(root, repo_name, zip_path, config)


def index_source_folder(source_path: str, repo_name: str, config: Config):
    root = os.path.abspath(source_path)
    _index_code_from_root(root, repo_name, root, config)
