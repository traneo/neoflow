"""Shared search tool functions used by both the agent and chat modules.

Provides Weaviate-backed search for code snippets, documentation, and tickets,
plus JSON action parsing utilities.
"""

import json
import logging
import re

import weaviate

from neoflow.config import Config
from neoflow.weaviate_client import create_weaviate_client

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# JSON action parsing utilities
# ---------------------------------------------------------------------------

def _extract_json_objects(text: str):
    """Yield all top-level JSON objects found in *text* using brace counting.

    This handles nested objects and arrays correctly, unlike a simple regex.
    """
    i = 0
    n = len(text)
    while i < n:
        if text[i] != "{":
            i += 1
            continue
        depth = 0
        in_string = False
        escape = False
        start = i
        for j in range(i, n):
            ch = text[j]
            if escape:
                escape = False
                continue
            if ch == "\\" and in_string:
                escape = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    yield text[start : j + 1]
                    i = j + 1
                    break
        else:
            break  # unclosed brace — stop scanning


def parse_action(text: str) -> dict | None:
    """Extract a JSON action block from an LLM response."""
    logger = logging.getLogger("parse_action")

    def _try_parse(candidate: str, source: str) -> dict | None:
        try:
            result = json.loads(candidate)
            if isinstance(result, dict) and "action" in result:
                logger.info("Parsed action from %s.", source)
                return result
        except json.JSONDecodeError as e:
            logger.warning("Failed to parse JSON from %s: %s", source, e)
        return None

    # 1. ```json fenced block (highest priority — explicitly requested format)
    fence_match = re.search(r"```json\s*\n(.*?)\n\s*```", text, re.DOTALL)
    if fence_match:
        result = _try_parse(fence_match.group(1), "```json fenced block")
        if result:
            return result

    # 2. Any code block
    code_block_match = re.search(r"```[a-zA-Z]*\s*\n(.*?)\n\s*```", text, re.DOTALL)
    if code_block_match:
        result = _try_parse(code_block_match.group(1), "generic code block")
        if result:
            return result

    # 3. Brace-counting scan — handles nested objects and multiline content
    logger.debug("Trying brace-counting scan for JSON object with 'action' key.")
    for candidate in _extract_json_objects(text):
        result = _try_parse(candidate, "brace-counted object")
        if result:
            return result

    # 4. Fix common cosmetic issues (single quotes, trailing commas) then retry
    logger.debug("Trying to fix common JSON issues in text.")
    fixed = re.sub(r",\s*([}\]])", r"\1", text.replace("'", '"'))
    for candidate in _extract_json_objects(fixed):
        result = _try_parse(candidate, "fixed JSON object")
        if result:
            return result

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
    return create_weaviate_client(config)


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
    include_comments: bool = True,
) -> str:
    """BM25 search on Tickets and optionally Comments, returning comprehensive results.
    
    Args:
        query: Search query text
        config: Configuration
        limit: Max tickets to return (default: 10)
        include_comments: Whether to search comments too and include in results (default: True)
    """
    client = _weaviate_client(config)
    try:
        if not client.collections.exists("Tickets"):
            return "Tickets collection does not exist. No imported tickets available."

        tickets = client.collections.use("Tickets")
        comments = client.collections.use("Comments") if client.collections.exists("Comments") else None

        # Search tickets
        result = tickets.query.bm25(
            query=query,
            limit=min(limit, 20),
            query_properties=["title", "url", "reference", "question"],
        )

        if not result.objects:
            return "No matching tickets found."

        # Collect unique ticket references
        ticket_refs = set()
        parts = []
        
        for obj in result.objects:
            props = obj.properties
            title = props.get("title", "?")
            ref = props.get("reference", "?")
            question = props.get("question", "")
            url = props.get("url", "")
            
            ticket_refs.add(ref)

            entry = f"--- {ref}: {title} ---"
            if question:
                # Truncate very long questions
                if len(question) > 500:
                    entry += f"\nQuestion: {question[:500]}... [truncated]"
                else:
                    entry += f"\nQuestion: {question}"
            if url:
                entry += f"\nURL: {url}"
            
            # Fetch related comments if requested
            if include_comments and comments:
                comment_result = comments.query.bm25(
                    query=query,
                    filters=weaviate.classes.query.Filter.by_property("reference").equal(ref),
                    limit=3,  # Top 3 most relevant comments per ticket
                )
                
                if comment_result.objects:
                    entry += "\n\nRelevant Comments:"
                    for i, comment_obj in enumerate(comment_result.objects, 1):
                        comment_text = comment_obj.properties.get("message", "")
                        # Truncate long comments
                        if len(comment_text) > 300:
                            comment_text = comment_text[:300] + "... [truncated]"
                        entry += f"\n  {i}. {comment_text}"
                    entry += "\n  (Use get_full_ticket action to see complete details)"
            
            parts.append(entry)

        return "\n\n".join(parts)
    finally:
        client.close()


def get_full_ticket(
    reference: str,
    config: Config,
) -> str:
    """Retrieve complete ticket details including ALL comments for deep research.
    
    Args:
        reference: Ticket reference ID (e.g., 'SDK-10007', 'TICKET-12345')
        config: Configuration
    
    Returns:
        Complete ticket with all comments, or error message if not found
    """
    client = _weaviate_client(config)
    try:
        if not client.collections.exists("Tickets"):
            return "Tickets collection does not exist."
        
        tickets = client.collections.use("Tickets")
        comments = client.collections.use("Comments") if client.collections.exists("Comments") else None
        
        # Find the ticket by reference
        result = tickets.query.fetch_objects(
            filters=weaviate.classes.query.Filter.by_property("reference").equal(reference),
            limit=1,
        )
        
        if not result.objects:
            return f"Ticket '{reference}' not found. Ensure you use the exact reference ID."
        
        # Get ticket details
        ticket_obj = result.objects[0]
        props = ticket_obj.properties
        title = props.get("title", "No title")
        question = props.get("question", "No question")
        url = props.get("url", "No URL")
        
        output = f"""╔═══════════════════════════════════════════════════════════════════
║ FULL TICKET DETAILS: {reference}
╠═══════════════════════════════════════════════════════════════════
║ Title: {title}
║ URL: {url}
╚═══════════════════════════════════════════════════════════════════

📋 QUESTION:
{question}
"""
        
        # Get ALL comments for this ticket
        if comments:
            comment_result = comments.query.fetch_objects(
                filters=weaviate.classes.query.Filter.by_property("reference").equal(reference),
                limit=100,  # Get up to 100 comments
            )
            
            if comment_result.objects:
                output += "\n" + "═" * 70 + "\n"
                output += f"💬 COMMENTS ({len(comment_result.objects)}):\n"
                output += "═" * 70 + "\n\n"
                
                for i, comment_obj in enumerate(comment_result.objects, 1):
                    comment_text = comment_obj.properties.get("message", "")
                    output += f"Comment {i}:\n{comment_text}\n\n{'-' * 70}\n\n"
            else:
                output += "\n(No comments found for this ticket)\n"
        else:
            output += "\n(Comments collection not available)\n"
        
        return output
        
    finally:
        client.close()


