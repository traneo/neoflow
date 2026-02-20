"""MCP tool definitions and schemas for NeoFlow.

Defines the schemas and wrapper functions for all MCP tools:
- ask_chat: Conversational AI with comprehensive search
- search_code: Search indexed code repositories
- search_documentation: Search documentation
- search_tickets: Search tickets/issues
"""

import logging
import sys
from typing import Any

from rich.console import Console

from neoflow.chat import run_chat
from neoflow.config import Config
from neoflow.search.tools import (
    search_code,
    search_documentation,
    search_tickets,
    get_full_ticket,
)
from neoflow.status_bar import StatusBar

logger = logging.getLogger(__name__)

# Tool schemas following JSON Schema specification
ASK_CHAT_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "The question or request to ask NeoFlow's conversational AI",
        },
        "include_code": {
            "type": "boolean",
            "default": True,
            "description": "Include code search results in the answer",
        },
        "include_docs": {
            "type": "boolean",
            "default": True,
            "description": "Include documentation search in the answer",
        },
        "include_tickets": {
            "type": "boolean",
            "default": True,
            "description": "Include ticket search in the answer",
        },
        "context": {
            "type": "string",
            "description": "Additional context for the query (optional)",
        },
    },
    "required": ["query"],
}

SEARCH_CODE_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "The search query text to find in code",
        },
        "limit": {
            "type": "integer",
            "minimum": 1,
            "maximum": 10,
            "default": 5,
            "description": "Maximum number of results to return",
        },
        "repository": {
            "type": "string",
            "description": "Filter by repository name (optional)",
        },
        "language": {
            "type": "string",
            "description": "Filter by programming language (optional)",
        },
        "is_test": {
            "type": "boolean",
            "description": "Filter test files: true for only tests, false to exclude tests (optional)",
        },
        "directory": {
            "type": "string",
            "description": "Filter by directory path (optional)",
        },
    },
    "required": ["query"],
}

SEARCH_DOCUMENTATION_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "The search query text to find in documentation",
        },
        "limit": {
            "type": "integer",
            "minimum": 1,
            "maximum": 10,
            "default": 5,
            "description": "Maximum number of results to return",
        },
    },
    "required": ["query"],
}

SEARCH_TICKETS_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "The search query text to find in tickets/issues",
        },
        "limit": {
            "type": "integer",
            "minimum": 1,
            "maximum": 20,
            "default": 10,
            "description": "Maximum number of results to return",
        },
    },
    "required": ["query"],
}

GET_FULL_TICKET_SCHEMA = {
    "type": "object",
    "properties": {
        "reference": {
            "type": "string",
            "description": "The exact ticket reference ID (e.g., 'SDK-10007', 'TICKET-12345')",
        },
    },
    "required": ["reference"],
}

# Tool wrapper functions
def tool_ask_chat(config: Config, arguments: dict[str, Any]) -> str:
    """Execute the ask_chat tool - conversational AI with comprehensive search.
    
    Args:
        config: Application configuration
        arguments: Tool arguments (query, include_code, include_docs, include_tickets, context)
    
    Returns:
        AI-generated response as markdown text
    """
    query = arguments["query"]
    context = arguments.get("context", "")
    
    # Append context if provided
    if context:
        query = f"{query}\n\nContext: {context}"
    
    logger.info(f"MCP ask_chat: {query[:100]}...")
    
    # Create console and disabled status bar for MCP execution
    # (status bar ANSI codes would interfere with JSON-RPC over stdio)
    console = Console(stderr=True)
    bar = StatusBar(output_file=sys.stderr, enabled=False)
    bar.start()
    
    try:
        result = run_chat(
            query=query,
            config=config,
            console=console,
            bar=bar,
            silent=True,  # Suppress console output for MCP
        )
        return result or "No response generated"
    except Exception as e:
        logger.error(f"ask_chat tool failed: {e}", exc_info=True)
        return f"Error: {str(e)}"
    finally:
        bar.stop()


def tool_search_code(config: Config, arguments: dict[str, Any]) -> str:
    """Execute the search_code tool - search indexed code repositories.
    
    Args:
        config: Application configuration
        arguments: Tool arguments (query, limit, repository, language, is_test, directory)
    
    Returns:
        Formatted code search results
    """
    query = arguments["query"]
    limit = arguments.get("limit", 5)
    repository = arguments.get("repository")
    language = arguments.get("language")
    is_test = arguments.get("is_test")
    directory = arguments.get("directory")
    
    logger.info(f"MCP search_code: {query[:100]}...")
    
    try:
        result = search_code(
            query=query,
            config=config,
            limit=limit,
            repository=repository,
            language=language,
            is_test=is_test,
            directory=directory,
        )
        return result
    except Exception as e:
        logger.error(f"search_code tool failed: {e}", exc_info=True)
        return f"Error: {str(e)}"


def tool_search_documentation(config: Config, arguments: dict[str, Any]) -> str:
    """Execute the search_documentation tool - search indexed documentation.
    
    Args:
        config: Application configuration
        arguments: Tool arguments (query, limit)
    
    Returns:
        Formatted documentation search results
    """
    query = arguments["query"]
    limit = arguments.get("limit", 5)
    
    logger.info(f"MCP search_documentation: {query[:100]}...")
    
    try:
        result = search_documentation(
            query=query,
            config=config,
            limit=limit,
        )
        return result
    except Exception as e:
        logger.error(f"search_documentation tool failed: {e}", exc_info=True)
        return f"Error: {str(e)}"


def tool_search_tickets(config: Config, arguments: dict[str, Any]) -> str:
    """Execute the search_tickets tool - search tickets and issues.
    
    Args:
        config: Application configuration
        arguments: Tool arguments (query, limit)
    
    Returns:
        Formatted ticket search results
    """
    query = arguments["query"]
    limit = arguments.get("limit", 10)
    
    logger.info(f"MCP search_tickets: {query[:100]}...")
    
    try:
        result = search_tickets(
            query=query,
            config=config,
            limit=limit,
        )
        return result
    except Exception as e:
        logger.error(f"search_tickets tool failed: {e}", exc_info=True)
        return f"Error: {str(e)}"


def tool_get_full_ticket(config: Config, arguments: dict[str, Any]) -> str:
    """Execute the get_full_ticket tool - retrieve complete ticket details.
    
    Args:
        config: Application configuration
        arguments: Tool arguments (reference)
    
    Returns:
        Complete ticket with all comments
    """
    reference = arguments["reference"]
    
    logger.info(f"MCP get_full_ticket: {reference}")
    
    try:
        result = get_full_ticket(
            reference=reference,
            config=config,
        )
        return result
    except Exception as e:
        logger.error(f"get_full_ticket tool failed: {e}", exc_info=True)
        return f"Error: {str(e)}"

