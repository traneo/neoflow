"""MCP server implementation for NeoFlow.

Main server that handles Model Context Protocol communication,
tool registration, and request processing.
"""

import asyncio
import logging
from typing import Any

from mcp.server import Server
from mcp.types import TextContent, Tool

from neoflow.config import Config
from neoflow.mcp.tools import (
    ASK_CHAT_SCHEMA,
    GITLAB_LIVE_SEARCH_SCHEMA,
    SEARCH_CODE_SCHEMA,
    SEARCH_DOCUMENTATION_SCHEMA,
    SEARCH_TICKETS_SCHEMA,
    GET_FULL_TICKET_SCHEMA,
    tool_ask_chat,
    tool_gitlab_live_search,
    tool_search_code,
    tool_search_documentation,
    tool_search_tickets,
    tool_get_full_ticket,
)

logger = logging.getLogger(__name__)


def create_mcp_server(config: Config | None = None) -> Server:
    """Create and configure the NeoFlow MCP server.
    
    Args:
        config: Application configuration. If None, loads from environment.
    
    Returns:
        Configured MCP Server instance
    """
    if config is None:
        config = Config.from_env()
    
    # Create MCP server with NeoFlow branding
    server = Server("neoflow")
    
    logger.info("Initializing NeoFlow MCP server")
    
    # Register tools
    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """List all available NeoFlow tools."""
        tools = [
            Tool(
                name="ask_chat",
                description=(
                    "Ask NeoFlow a question using conversational AI. "
                    "This is the most powerful tool - it intelligently searches across "
                    "code, documentation, and tickets, then provides a comprehensive answer "
                    "with examples, explanations, and references. "
                    "Use this for: understanding code, finding implementations, "
                    "troubleshooting issues, learning best practices."
                ),
                inputSchema=ASK_CHAT_SCHEMA,
            ),
            Tool(
                name="search_code",
                description=(
                    "Search indexed code repositories with advanced filtering. "
                    "Returns code snippets with metadata (file paths, line numbers, "
                    "definitions, imports). Use when you need direct access to code "
                    "without AI interpretation."
                ),
                inputSchema=SEARCH_CODE_SCHEMA,
            ),
            Tool(
                name="search_documentation",
                description=(
                    "Search indexed documentation for relevant information. "
                    "Returns documentation sections with file paths. "
                    "Use for finding setup guides, API docs, and other documentation."
                ),
                inputSchema=SEARCH_DOCUMENTATION_SCHEMA,
            ),
            Tool(
                name="search_tickets",
                description=(
                    "Search support tickets, issues, and bug reports using BM25 search. "
                    "Returns ticket titles, references, questions, URLs, and top relevant comments. "
                    "Use for finding known issues, bug reports, and support history. "
                    "Follow up with get_full_ticket to see complete details."
                ),
                inputSchema=SEARCH_TICKETS_SCHEMA,
            ),
            Tool(
                name="get_full_ticket",
                description=(
                    "Retrieve COMPLETE ticket details including ALL comments for deep research. "
                    "Use this after search_tickets finds relevant tickets to understand: "
                    "how issues were resolved, workarounds and solutions, complete conversation history, "
                    "and implementation details from discussions. "
                    "Requires the exact ticket reference ID (e.g., 'SDK-10007')."
                ),
                inputSchema=GET_FULL_TICKET_SCHEMA,
            ),
            Tool(
                name="gitlab_live_search",
                description=(
                    "Perform real-time search on GitLab repositories via API. "
                    "Returns code snippets directly from GitLab with URLs. "
                    "Use when you need the most up-to-date code from GitLab, "
                    "or when searching repositories not yet indexed."
                ),
                inputSchema=GITLAB_LIVE_SEARCH_SCHEMA,
            ),
        ]
        
        logger.info(f"Listed {len(tools)} MCP tools")
        return tools
    
    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any] | None) -> list[TextContent]:
        """Handle tool invocation.
        
        Args:
            name: Tool name to execute
            arguments: Tool arguments from client
        
        Returns:
            List of TextContent responses
        """
        if arguments is None:
            arguments = {}
        
        logger.info(f"MCP tool called: {name}")
        logger.debug(f"Tool arguments: {arguments}")
        
        try:
            # Route to appropriate tool handler
            if name == "ask_chat":
                result = await asyncio.to_thread(tool_ask_chat, config, arguments)
            elif name == "search_code":
                result = await asyncio.to_thread(tool_search_code, config, arguments)
            elif name == "search_documentation":
                result = await asyncio.to_thread(tool_search_documentation, config, arguments)
            elif name == "search_tickets":
                result = await asyncio.to_thread(tool_search_tickets, config, arguments)
            elif name == "get_full_ticket":
                result = await asyncio.to_thread(tool_get_full_ticket, config, arguments)
            elif name == "gitlab_live_search":
                result = await asyncio.to_thread(tool_gitlab_live_search, config, arguments)
            else:
                error_msg = f"Unknown tool: {name}"
                logger.error(error_msg)
                return [TextContent(type="text", text=f"❌ Error: {error_msg}")]
            
            logger.info(f"Tool {name} completed successfully")
            return [TextContent(type="text", text=result)]
        
        except Exception as e:
            error_msg = f"Tool execution failed: {str(e)}"
            logger.error(f"{error_msg}", exc_info=True)
            return [TextContent(type="text", text=f"❌ Error: {error_msg}")]
    
    logger.info("NeoFlow MCP server initialized successfully")
    return server


async def run_mcp_server(transport: str = "stdio", config: Config | None = None) -> None:
    """Run the MCP server with specified transport.
    
    Args:
        transport: Transport type ("stdio" or "sse")
        config: Application configuration
    """
    if config is None:
        config = Config.from_env()
    
    server = create_mcp_server(config)
    
    if transport == "stdio":
        from mcp.server.stdio import stdio_server
        
        logger.info("Starting MCP server with stdio transport")
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
            )
    
    elif transport == "sse":
        from mcp.server.sse import SseServerTransport
        from starlette.applications import Starlette
        from starlette.responses import PlainTextResponse
        from starlette.routing import Route
        
        logger.info(f"Starting MCP server with SSE transport on {config.mcp.sse_host}:{config.mcp.sse_port}")
        
        sse = SseServerTransport("/messages")

        class SseEndpoint:
            async def __call__(self, scope, receive, send):
                if scope["method"] != "GET":
                    response = PlainTextResponse("Method Not Allowed", status_code=405)
                    await response(scope, receive, send)
                    return

                async with sse.connect_sse(scope, receive, send) as streams:
                    await server.run(
                        streams[0], streams[1], server.create_initialization_options()
                    )

        class MessagesEndpoint:
            async def __call__(self, scope, receive, send):
                if scope["method"] != "POST":
                    response = PlainTextResponse("Method Not Allowed", status_code=405)
                    await response(scope, receive, send)
                    return

                await sse.handle_post_message(scope, receive, send)
        
        app = Starlette(
            routes=[
                Route("/sse", endpoint=SseEndpoint()),
                Route("/messages", endpoint=MessagesEndpoint(), methods=["POST"]),
            ]
        )
        
        import uvicorn
        config_uv = uvicorn.Config(
            app, 
            host=config.mcp.sse_host, 
            port=config.mcp.sse_port,
            log_level="info"
        )
        server_uv = uvicorn.Server(config_uv)
        await server_uv.serve()
    
    else:
        raise ValueError(f"Unknown transport: {transport}. Must be 'stdio' or 'sse'")
