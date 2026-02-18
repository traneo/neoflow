"""Shared search tool functions used by both the agent and chat modules.

Provides Weaviate-backed search for code snippets, documentation, and tickets,
plus JSON action parsing utilities.
"""

import json
import logging
import re

import weaviate
from weaviate.config import AdditionalConfig, Timeout

from neoflow.config import Config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# JSON action parsing utilities
# ---------------------------------------------------------------------------

def parse_action(text: str) -> dict | None:
    """Extract a JSON action block from an LLM response."""
    logger = logging.getLogger("parse_action")
    # 1. Try to find JSON in ```json fences first
    fence_match = re.search(r"```json\s*\n(.*?)\n\s*```", text, re.DOTALL)
    if fence_match:
        json_str = fence_match.group(1)
        logger.debug("Trying to parse JSON from ```json fenced block.")
        try:
            result = json.loads(json_str)
            logger.info("Parsed action from ```json fenced block.")
            return result
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON from ```json fenced block: {e}")

    # 2. Try to find JSON in any code block (not just json)
    code_block_match = re.search(r"```[a-zA-Z]*\s*\n(.*?)\n\s*```", text, re.DOTALL)
    if code_block_match:
        code_str = code_block_match.group(1)
        logger.debug("Trying to parse JSON from generic code block.")
        try:
            result = json.loads(code_str)
            logger.info("Parsed action from generic code block.")
            return result
        except Exception as e:
            logger.warning(f"Failed to parse JSON from generic code block: {e}")

    # 3. Try to extract the first valid JSON object anywhere in the text
    logger.debug("Trying to parse JSON from any object with 'action' key in text.")
    for match in re.finditer(r"\{[^{}]*\"action\"[^{}]*\}", text):
        try:
            parsed = json.loads(match.group())
            if "action" in parsed:
                logger.info("Parsed action from loose JSON object in text.")
                return parsed
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON object from text: {e}")
            continue

    # 4. Try to fix common JSON issues (single quotes, trailing commas)
    logger.debug("Trying to fix common JSON issues in text.")
    fixed_text = text.replace("'", '"')
    fixed_text = re.sub(r',\s*([}\]])', r'\1', fixed_text)  # remove trailing commas
    try:
        parsed = json.loads(fixed_text)
        if isinstance(parsed, dict) and "action" in parsed:
            logger.info("Parsed action from fixed JSON text.")
            return parsed
    except Exception as e:
        logger.warning(f"Failed to parse after fixing common JSON issues: {e}")

    logger.debug("Failed to parse any action from response text.")
    return None


def strip_json_blocks(text: str) -> str:
    """Remove ```json ... ``` fenced blocks from an LLM response."""
    return re.sub(r"```json\s*\n.*?\n\s*```", "", text, flags=re.DOTALL)


# ---------------------------------------------------------------------------
# Weaviate connection helper
# ---------------------------------------------------------------------------

def _weaviate_client(config: Config):
    """Create a Weaviate client using the app config."""
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


# ---------------------------------------------------------------------------
# Search tools
# ---------------------------------------------------------------------------

def search_code(
    query: str,
    config: Config,
    limit: int = 5,
    repository: str | None = None,
    language: str | None = None,
    is_test: bool | None = None,
    directory: str | None = None,
) -> str:
    """Hybrid search on the Weaviate CodeSnippets collection, returning rich snippets."""
    client = _weaviate_client(config)
    try:
        if not client.collections.exists("CodeSnippets"):
            return "CodeSnippets collection does not exist. No indexed code available."

        snippets = client.collections.use("CodeSnippets")

        from weaviate.classes.query import Filter

        filter_clauses = []
        if repository:
            filter_clauses.append(Filter.by_property("repository").equal(repository))
        if language:
            filter_clauses.append(Filter.by_property("language").equal(language))
        if is_test is not None:
            filter_clauses.append(Filter.by_property("is_test").equal(is_test))
        if directory:
            filter_clauses.append(Filter.by_property("directory").like(f"{directory}*"))

        filters = None
        if len(filter_clauses) == 1:
            filters = filter_clauses[0]
        elif len(filter_clauses) > 1:
            filters = Filter.all_of(filter_clauses)

        result = snippets.query.hybrid(
            query=query,
            alpha=0.5,
            limit=min(limit, 10),
            filters=filters,
        )

        if not result.objects:
            return "No matching code snippets found."

        parts = []
        for obj in result.objects:
            props = obj.properties

            repo = props.get("repository", "?")
            fpath = props.get("file_path", "?")
            lang = props.get("language", "?")
            line_start = props.get("line_start")
            line_end = props.get("line_end")
            chunk_idx = props.get("chunk_index")
            total = props.get("total_chunks")

            location = f"{repo} | {fpath}"
            if line_start and line_end:
                location += f" (L{line_start}-L{line_end})"
            if total and total > 1 and chunk_idx is not None:
                location += f" [chunk {chunk_idx + 1}/{total}]"

            header = f"--- {location} ({lang}) ---"

            meta_parts = []
            test_flag = props.get("is_test")
            if test_flag:
                meta_parts.append("TEST FILE")
            directory_val = props.get("directory")
            if directory_val and directory_val != ".":
                meta_parts.append(f"dir: {directory_val}")
            definitions = props.get("definitions")
            if definitions:
                meta_parts.append(f"defines: {definitions}")
            imports = props.get("imports")
            if imports:
                import_list = imports.split("\n")
                if len(import_list) > 5:
                    import_list = import_list[:5] + [f"... +{len(import_list) - 5} more"]
                meta_parts.append(f"imports: {', '.join(import_list)}")

            content = props.get("content", "")
            url = props.get("url", "")

            entry = header
            if meta_parts:
                entry += "\n[" + " | ".join(meta_parts) + "]"
            entry += "\n" + content
            if url:
                entry += f"\nURL: {url}"
            parts.append(entry)

        return "\n\n".join(parts)
    finally:
        client.close()


def search_documentation(
    query: str,
    config: Config,
    limit: int = 5,
) -> str:
    """Hybrid search on the Weaviate Documentation collection, returning raw content."""
    client = _weaviate_client(config)
    try:
        if not client.collections.exists("Documentation"):
            return "Documentation collection does not exist. No imported documentation available."

        docs = client.collections.use("Documentation")

        result = docs.query.hybrid(
            query=query,
            alpha=0.5,
            limit=min(limit, 10),
        )

        if not result.objects:
            return "No matching documentation found."

        parts = []
        for obj in result.objects:
            props = obj.properties
            header = f"--- {props.get('file_path', '?')} ---"
            content = props.get("content", "")
            parts.append(header + "\n" + content)

        return "\n\n".join(parts)
    finally:
        client.close()


def search_tickets(
    query: str,
    config: Config,
    limit: int = 10,
) -> str:
    """BM25 search on the Weaviate Tickets collection, returning formatted results."""
    client = _weaviate_client(config)
    try:
        if not client.collections.exists("Tickets"):
            return "Tickets collection does not exist. No imported tickets available."

        tickets = client.collections.use("Tickets")

        result = tickets.query.bm25(
            query=query,
            limit=min(limit, 20),
            query_properties=["title", "url", "reference", "question"],
        )

        if not result.objects:
            return "No matching tickets found."

        parts = []
        for obj in result.objects:
            props = obj.properties
            title = props.get("title", "?")
            ref = props.get("reference", "?")
            question = props.get("question", "")
            url = props.get("url", "")

            entry = f"--- {ref}: {title} ---"
            if question:
                entry += f"\nQuestion: {question}"
            if url:
                entry += f"\nURL: {url}"
            parts.append(entry)

        return "\n\n".join(parts)
    finally:
        client.close()


def gitlab_live_search(query: str, config: Config, repository: str | None = None, limit: int = 10) -> str:
    """Search GitLab API in real-time for code.
    
    Args:
        query: Search query text
        config: Configuration with GitLab settings
        repository: Optional repository path (e.g. "tdecu/tdecu"). If provided, searches only that repo
        limit: Maximum results to return (default 10)
    
    Returns:
        Formatted code search results or empty string if no results
    """
    if not config.gitlab.api_token:
        logger.debug("No GITLAB_TOKEN set, skipping live search")
        return "GitLab live search not available (no API token configured)"
    
    logger.info("Running GitLab live code search for query: '%s' in repo: %s", query, repository or "all")
    
    try:
        from neoflow.gitlab.api import GitLabClient
        
        # Split query into words, skip common stop words
        stop_words = {
            "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
            "have", "has", "had", "do", "does", "did", "will", "would", "shall",
            "should", "may", "might", "must", "can", "could", "of", "in", "to",
            "for", "with", "on", "at", "from", "by", "about", "as", "into",
            "through", "during", "before", "after", "and", "but", "or", "nor",
            "not", "so", "yet", "both", "either", "neither", "each", "every",
            "all", "any", "few", "more", "most", "other", "some", "such", "no",
            "only", "own", "same", "than", "too", "very", "just", "because",
            "how", "what", "which", "who", "whom", "this", "that", "these",
            "those", "i", "me", "my", "we", "our", "you", "your", "he", "him",
            "she", "her", "it", "its", "they", "them", "their", "if", "when",
            "where", "why", "am", "using", "use", "used",
        }
        
        words = [w for w in query.split() if w.lower() not in stop_words and len(w) > 1]
        if not words:
            words = [w for w in query.split() if len(w) > 1]
        
        logger.info("Search words: %s", words)
        
        all_results = []
        
        with GitLabClient(config.gitlab) as gl:
            # Determine which projects to search
            projects = []
            if repository:
                projects = [repository]
            else:
                group_path = config.gitlab.gitlab_group_path.rstrip("/")
                if group_path:
                    projects = [group_path]
            
            if not projects:
                logger.warning("No projects configured for search")
                return "No projects configured for GitLab search"
            
            for project_id in projects:
                for word in words:
                    try:
                        results = gl.search_project_code(
                            project_id, word, max_results=min(limit // len(words) + 1, 20),
                        )
                        all_results.extend(results)
                    except Exception as e:
                        logger.warning(
                            "Project search in %s for '%s' failed: %s",
                            project_id, word, e,
                        )
        
        if not all_results:
            return f"No code found in GitLab for query: {query}"
        
        # Deduplicate by file path
        seen = set()
        unique = []
        for r in all_results:
            key = f"{r.project_id}:{r.file_path}"
            if key not in seen:
                seen.add(key)
                unique.append(r)
        
        # Format results
        parts = []
        for r in unique[:limit]:
            snippet = r.content[:500] if len(r.content) > 500 else r.content
            parts.append(f"## {r.project_name} — {r.file_path}\n```\n{snippet}\n```\nURL: {r.url}")
        
        return "\n\n".join(parts) if parts else "No results returned from GitLab"
        
    except Exception as e:
        logger.warning("GitLab live search failed: %s", e)
        return f"GitLab search error: {str(e)}"

