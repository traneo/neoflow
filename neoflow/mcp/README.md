# NeoFlow MCP Server Module

This module implements the Model Context Protocol (MCP) server for NeoFlow, enabling integration with AI coding assistants.

## Structure

- `__init__.py` - Module initialization and exports
- `server.py` - Main MCP server implementation and protocol handling
- `tools.py` - Tool definitions, schemas, and wrapper functions

## Available Tools

### 1. ask_chat (Recommended)
Conversational AI that combines all search capabilities with intelligent reasoning.
- Query NeoFlow with natural language questions
- Get comprehensive answers with code examples and explanations
- Automatically searches across code, docs, and tickets

### 2. search_code
Direct search of indexed code repositories with advanced filtering.
- Search by repository, language, directory
- Filter test files
- Returns code snippets with metadata

### 3. search_documentation
Search indexed documentation for relevant information.
- Search all imported documentation
- Get documentation sections with file paths

### 4. search_tickets
Search support tickets, issues, and bug reports.
- BM25 search across tickets
- Returns ticket titles, references, and URLs

### 5. get_full_ticket
Retrieve complete ticket details including ALL comments.
- Get full ticket with all comments for deep research
- Use after finding relevant tickets via search_tickets
- Returns complete conversation thread

## Usage

The MCP server is started via the CLI command:

```bash
neoflow mcp-server
```

This starts the server in stdio mode, which is the standard for MCP servers.

## Configuration

MCP settings are configured via environment variables or the Config object:

- `MCP_ENABLED` - Enable/disable MCP server (default: true)
- `MCP_TRANSPORT` - Transport type: "stdio" or "sse" (default: stdio)
- `MCP_SSE_HOST` - Host for SSE transport (default: localhost)
- `MCP_SSE_PORT` - Port for SSE transport (default: 9721)
- `MCP_TIMEOUT_SECONDS` - Request timeout (default: 30)
- `MCP_AUTH_REQUIRED` - Require authentication (default: false)
- `MCP_AUTH_TOKEN` - Authentication token if required

## Integration

See the main documentation in `docs/MCP_INTEGRATION.md` for setup instructions with:
- VS Code with GitHub Copilot
- Claude Desktop
- Cursor IDE
- Other MCP clients
