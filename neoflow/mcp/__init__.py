"""Model Context Protocol (MCP) server for NeoFlow.

Exposes NeoFlow's search and chat capabilities via the Model Context Protocol,
enabling integration with AI coding assistants like GitHub Copilot, Claude Desktop,
and other MCP clients.
"""

from neoflow.mcp.server import create_mcp_server

__all__ = ["create_mcp_server"]
