# MCP Integration Guide

NeoFlow provides a Model Context Protocol (MCP) server that exposes its powerful search and AI capabilities to MCP-compatible clients like GitHub Copilot, Claude Desktop, Cursor IDE, and other AI coding assistants.

## Table of Contents

- [What is MCP?](#what-is-mcp)
- [Features](#features)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Available Tools](#available-tools)
- [Client Setup](#client-setup)
- [Usage Examples](#usage-examples)
- [Troubleshooting](#troubleshooting)
- [Advanced Configuration](#advanced-configuration)

---

## What is MCP?

The Model Context Protocol (MCP) is an open protocol that standardizes how AI applications provide context to Large Language Models. It enables:

- **Tools**: Functions that LLMs can invoke to perform actions
- **Resources**: Data sources that provide context to LLMs  
- **Prompts**: Reusable prompt templates

NeoFlow implements MCP to expose its search capabilities as tools that AI assistants can use to search your codebase, documentation, tickets, and GitLab repositories.

---

## Features

✅ **5 Powerful Tools**
- `ask_chat` - Conversational AI with comprehensive search (⭐ Recommended)
- `search_code` - Indexed code search with filters
- `search_documentation` - Documentation search
- `search_tickets` - Ticket/issue search
- `gitlab_live_search` - Real-time GitLab API search

✅ **Universal Integration**
- Works with VS Code + GitHub Copilot
- Works with Claude Desktop
- Works with Cursor IDE
- Compatible with any MCP client

✅ **Easy Setup**
- Single command to start: `neoflow mcp-server`
- Automatic tool registration
- No additional configuration required

---

## Prerequisites

1. **NeoFlow Installation**
   ```bash
   pip install -e .
   ```

2. **Weaviate Running**
   ```bash
   docker compose up -d
   ```

3. **Indexed Data**
   - Import code: `neoflow import-zip -f /path/to/repo.zip -n repo-name`
   - Import docs: `neoflow import-documentation --path /path/to/docs`
   - Index GitLab: `neoflow gitlab-index`

4. **MCP Client**
   - VS Code with GitHub Copilot extension, or
   - Claude Desktop, or
   - Cursor IDE

---

## Quick Start

### 1. Start the MCP Server

```bash
neoflow mcp-server
```

The server will start in stdio mode and wait for MCP protocol messages.

### 2. Configure Your MCP Client

**VS Code (User Settings JSON):**
```json
{
  "github.copilot.chat.mcp.servers": {
    "neoflow": {
      "command": "neoflow",
      "args": ["mcp-server"]
    }
  }
}
```

**Claude Desktop:**

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):
```json
{
  "mcpServers": {
    "neoflow": {
      "command": "neoflow",
      "args": ["mcp-server"]
    }
  }
}
```

### 3. Restart Your Client

Restart VS Code or Claude Desktop to load the MCP server configuration.

### 4. Test It

In GitHub Copilot Chat or Claude, try:
- "Search for authentication code in the backend repository"
- "How does the payment processing work?"
- "Find tickets about login issues"

---

## Configuration

### Environment Variables

Configure NeoFlow's MCP server via environment variables:

```bash
# MCP Server Configuration
export MCP_ENABLED=true                 # Enable/disable MCP (default: true)
export MCP_TRANSPORT=stdio              # Transport: stdio or sse (default: stdio)
export MCP_SSE_HOST=localhost           # SSE host (default: localhost)
export MCP_SSE_PORT=9721                # SSE port (default: 9721)
export MCP_TIMEOUT_SECONDS=30           # Request timeout (default: 30)
export MCP_AUTH_REQUIRED=false          # Require auth (default: false)
export MCP_AUTH_TOKEN=your-token        # Auth token if required

# NeoFlow Configuration
export WEAVIATE_HOST=localhost
export WEAVIATE_PORT=8080
export GITLAB_TOKEN=your-gitlab-token
export LLM_PROVIDER=ollama              # or openai, vllm
export OLLAMA_MODEL=glm-4.7-flash
```

### Command Line Options

```bash
# Start with specific transport
neoflow mcp-server --transport stdio
neoflow mcp-server --transport sse

# Use with custom environment
MCP_TIMEOUT_SECONDS=60 neoflow mcp-server
```

---

## Available Tools

### 1. ask_chat ⭐ (Recommended)

**Description:** Conversational AI that intelligently searches across all data sources and provides comprehensive answers.

**When to use:**
- Understanding how code works
- Finding implementations with explanations
- Troubleshooting issues
- Learning best practices from your codebase
- Getting code examples in context

**Parameters:**
- `query` (string, required): Your question or request
- `include_code` (boolean, optional): Include code search (default: true)
- `include_docs` (boolean, optional): Include documentation (default: true)
- `include_tickets` (boolean, optional): Include tickets (default: true)
- `context` (string, optional): Additional context

**Example:**
```
How does authentication work in this project? Show me the implementation.
```

**Response:** Comprehensive answer with code snippets, explanations, file references, and related documentation.

---

### 2. search_code

**Description:** Direct hybrid search on indexed code repositories with advanced filtering.

**When to use:**
- Need raw code snippets without AI interpretation
- Searching with specific filters (language, directory, etc.)
- Finding definitions and imports
- Locating test files

**Parameters:**
- `query` (string, required): Search query
- `limit` (integer, optional): Max results 1-10 (default: 5)
- `repository` (string, optional): Filter by repository name
- `language` (string, optional): Filter by language (e.g., "python", "javascript")
- `is_test` (boolean, optional): Filter test files (true) or exclude tests (false)
- `directory` (string, optional): Filter by directory path

**Example:**
```json
{
  "query": "authentication middleware",
  "language": "python",
  "repository": "backend",
  "limit": 5
}
```

---

### 3. search_documentation

**Description:** Search indexed documentation for relevant information.

**When to use:**
- Finding setup instructions
- Looking for API documentation
- Reading guides and tutorials
- Understanding configuration options

**Parameters:**
- `query` (string, required): Search query
- `limit` (integer, optional): Max results 1-10 (default: 5)

**Example:**
```json
{
  "query": "database configuration setup",
  "limit": 3
}
```

---

### 4. search_tickets

**Description:** BM25 search on tickets, issues, and bug reports.

**When to use:**
- Finding known issues
- Looking for bug reports
- Searching support history
- Understanding past problems

**Parameters:**
- `query` (string, required): Search query
- `limit` (integer, optional): Max results 1-20 (default: 10)

**Example:**
```json
{
  "query": "payment gateway timeout",
  "limit": 10
}
```

---

### 5. gitlab_live_search

**Description:** Real-time search on GitLab repositories via API (not indexed).

**When to use:**
- Need the most up-to-date code
- Searching repositories not yet indexed
- Looking for recent changes
- Verifying current implementations

**Parameters:**
- `query` (string, required): Search query
- `repository` (string, optional): Specific repository (e.g., "group/repo")
- `limit` (integer, optional): Max results 1-20 (default: 10)

**Example:**
```json
{
  "query": "database migration",
  "repository": "backend/api",
  "limit": 5
}
```

---

## Client Setup

### VS Code with GitHub Copilot

1. **Install GitHub Copilot Extension**
   - Open VS Code
   - Install "GitHub Copilot" and "GitHub Copilot Chat" extensions

2. **Configure MCP Server**
   - Open Settings (JSON): `Cmd/Ctrl + Shift + P` → "Preferences: Open User Settings (JSON)"
   - Add NeoFlow MCP configuration:

   ```json
   {
     "github.copilot.chat.mcp.servers": {
       "neoflow": {
         "command": "/path/to/neoflow",
         "args": ["mcp-server"],
         "env": {
           "PYTHONUNBUFFERED": "1",
           "WEAVIATE_HOST": "localhost",
           "GITLAB_TOKEN": "your-token"
         }
       }
     }
   }
   ```

3. **Find NeoFlow Path**
   ```bash
   which neoflow  # Linux/Mac
   where neoflow  # Windows
   ```

4. **Restart VS Code**

5. **Test in Copilot Chat**
   - Open Copilot Chat panel
   - Try: "Search for authentication code"

---

### Claude Desktop

1. **Install Claude Desktop**
   - Download from https://claude.ai/download

2. **Create/Edit Configuration File**

   **macOS:**
   ```bash
   mkdir -p ~/Library/Application\ Support/Claude
   nano ~/Library/Application\ Support/Claude/claude_desktop_config.json
   ```

   **Windows:**
   ```bash
   mkdir %APPDATA%\Claude
   notepad %APPDATA%\Claude\claude_desktop_config.json
   ```

   **Linux:**
   ```bash
   mkdir -p ~/.config/Claude
   nano ~/.config/Claude/claude_desktop_config.json
   ```

3. **Add Configuration**
   ```json
   {
     "mcpServers": {
       "neoflow": {
         "command": "/path/to/neoflow",
         "args": ["mcp-server"],
         "env": {
           "PYTHONUNBUFFERED": "1"
         }
       }
     }
   }
   ```

4. **Restart Claude Desktop**

5. **Verify Tools**
   - Open Claude
   - Check for tool availability indicator
   - Try asking Claude to search your codebase

---

### Cursor IDE

Cursor uses a similar configuration to VS Code:

1. **Open Cursor Settings**
2. **Add MCP Server** in settings.json
3. **Restart Cursor**

Configuration format:
```json
{
  "mcp.servers": {
    "neoflow": {
      "command": "neoflow",
      "args": ["mcp-server"]
    }
  }
}
```

---

## Usage Examples

### Example 1: Understanding Authentication

**Prompt to AI Assistant:**
> How does authentication work in this project? Show me the implementation and explain the flow.

**What happens:**
1. AI assistant calls `ask_chat` tool
2. NeoFlow searches code, docs, and tickets
3. Provides comprehensive answer with:
   - Authentication flow explanation
   - Code snippets from auth middleware
   - Related documentation
   - Security considerations
   - Known issues from tickets

---

### Example 2: Finding a Bug Pattern

**Prompt to AI Assistant:**
> Find all places where we catch exceptions without logging them

**What happens:**
1. AI assistant calls `search_code` tool
2. Searches for exception handling patterns
3. Returns code locations with context
4. AI analyzes and summarizes findings

---

### Example 3: Researching an Issue

**Prompt to AI Assistant:**
> Why are payment processing requests timing out? Check tickets and code.

**What happens:**
1. AI assistant calls `search_tickets` for timeout issues
2. Calls `search_code` for payment processing implementation
3. Combines findings to explain likely causes
4. References specific tickets and code locations

---

### Example 4: Finding Recent Changes

**Prompt to AI Assistant:**
> What are the latest changes to the API authentication in GitLab?

**What happens:**
1. AI assistant calls `gitlab_live_search`
2. Gets real-time results from GitLab
3. Shows recent code with URLs
4. AI explains the changes

---

## Troubleshooting

### MCP Server Won't Start

**Error:** `Cannot connect to Weaviate`

**Solution:**
```bash
# Start Weaviate
docker compose up -d

# Verify it's running
docker compose ps
```

---

**Error:** `ModuleNotFoundError: No module named 'mcp'`

**Solution:**
```bash
# Install MCP dependency
pip install mcp>=0.9.0

# Or reinstall NeoFlow
pip install -e .
```

---

### Tools Not Appearing in VS Code

**Issue:** GitHub Copilot doesn't show NeoFlow tools

**Solutions:**

1. **Check Configuration Path**
   ```bash
   # Find neoflow binary
   which neoflow
   
   # Use full path in settings.json
   ```

2. **Check Settings Location**
   - User settings: `~/.config/Code/User/settings.json` (Linux)
   - User settings: `~/Library/Application Support/Code/User/settings.json` (Mac)
   - User settings: `%APPDATA%\Code\User\settings.json` (Windows)

3. **Reload VS Code**
   - `Cmd/Ctrl + Shift + P` → "Developer: Reload Window"

4. **Check VS Code Output**
   - View → Output → Select "GitHub Copilot" or "MCP"
   - Look for connection errors

---

### Claude Desktop Can't Connect

**Issue:** Claude doesn't recognize NeoFlow tools

**Solutions:**

1. **Verify Config File Location**
   ```bash
   # macOS
   cat ~/Library/Application\ Support/Claude/claude_desktop_config.json
   
   # Linux
   cat ~/.config/Claude/claude_desktop_config.json
   ```

2. **Check JSON Syntax**
   - Ensure valid JSON (no trailing commas)
   - Use a JSON validator

3. **Check Logs**
   - macOS: `~/Library/Logs/Claude/`
   - Look for MCP connection errors

4. **Use Full Path**
   ```bash
   # Get full path
   which neoflow
   
   # Use in config
   "command": "/home/user/.local/bin/neoflow"
   ```

---

### Permission Denied Error

**Error:** `Permission denied: 'neoflow'`

**Solution:**
```bash
# Make executable
chmod +x $(which neoflow)

# Or use Python directly
"command": "python",
"args": ["-m", "neoflow.cli", "mcp-server"]
```

---

### Timeout Errors

**Error:** `Tool execution timed out`

**Solutions:**

1. **Increase Timeout**
   ```bash
   export MCP_TIMEOUT_SECONDS=60
   neoflow mcp-server
   ```

2. **Or in MCP config:**
   ```json
   {
     "mcpServers": {
       "neoflow": {
         "command": "neoflow",
         "args": ["mcp-server"],
         "env": {
           "MCP_TIMEOUT_SECONDS": "60"
         }
       }
     }
   }
   ```

3. **Optimize Weaviate**
   - Ensure Weaviate has enough resources
   - Check Docker container limits

---

### Empty Search Results

**Issue:** Tools return "No results found"

**Solutions:**

1. **Verify Data is Indexed**
   ```bash
   # Check collections exist
   docker compose exec weaviate weaviate-cli collections list
   ```

2. **Import Data**
   ```bash
   # Import code
   neoflow import-zip -f /path/to/repo.zip -n repo-name
   
   # Import documentation
   neoflow import-documentation --path /path/to/docs
   ```

3. **Check Search Query**
   - Try broader search terms
   - Use `ask_chat` instead of specific search tools

---

## Advanced Configuration

### Using with Custom Python Environment

If NeoFlow is in a virtual environment:

```json
{
  "mcpServers": {
    "neoflow": {
      "command": "/path/to/venv/bin/python",
      "args": ["-m", "neoflow.cli", "mcp-server"],
      "env": {
        "PYTHONPATH": "/path/to/neoflow",
        "VIRTUAL_ENV": "/path/to/venv"
      }
    }
  }
}
```

---

### SSE Transport (Web Clients)

For web-based MCP clients:

```bash
# Start with SSE transport
neoflow mcp-server --transport sse
```

Server will listen on `http://localhost:9721`

Configure client to connect to:
- SSE endpoint: `http://localhost:9721/sse`
- Messages endpoint: `http://localhost:9721/messages`

---

### Multiple Environments

Run different MCP servers for different projects:

```json
{
  "mcpServers": {
    "neoflow-project-a": {
      "command": "neoflow",
      "args": ["mcp-server"],
      "env": {
        "WEAVIATE_HOST": "localhost",
        "WEAVIATE_PORT": "8080"
      }
    },
    "neoflow-project-b": {
      "command": "neoflow",
      "args": ["mcp-server"],
      "env": {
        "WEAVIATE_HOST": "localhost",
        "WEAVIATE_PORT": "8081"
      }
    }
  }
}
```

---

### Authentication

Enable authentication for production:

```bash
export MCP_AUTH_REQUIRED=true
export MCP_AUTH_TOKEN=your-secure-token
neoflow mcp-server
```

Configure client:
```json
{
  "mcpServers": {
    "neoflow": {
      "command": "neoflow",
      "args": ["mcp-server"],
      "env": {
        "MCP_AUTH_TOKEN": "your-secure-token"
      }
    }
  }
}
```

---

## Best Practices

### 1. Use ask_chat for Most Queries

The `ask_chat` tool is the most powerful and user-friendly. It automatically:
- Searches across all data sources
- Provides context and explanations
- References specific files and line numbers
- Combines multiple search results

**Use specific search tools only when:**
- You need raw search results
- You want fine-grained control over filters
- You're building custom workflows

---

### 2. Keep Data Fresh

Regularly update indexed data:

```bash
# Refresh GitLab repositories
neoflow gitlab-refresh

# Re-import updated documentation
neoflow import-documentation --path /path/to/docs

# Import new code archives
neoflow import-zip -f /path/to/updated-repo.zip -n repo-name
```

---

### 3. Optimize Search Queries

**Good queries:**
- "authentication middleware in Python"
- "payment processing timeout errors"
- "API endpoints for user management"

**Less effective:**
- "code" (too broad)
- "fix bug" (too vague)
- Single keywords (use phrases)

---

### 4. Monitor Performance

Check MCP server logs:

```bash
# Run with verbose logging
neoflow -v mcp-server

# Check for slow queries
tail -f ~/.neoflow/logs/mcp.log
```

---

### 5. Security Considerations

- **Local Use Only**: MCP stdio transport is designed for local use
- **Sensitive Data**: Be aware tools can access all indexed data
- **GitLab Tokens**: Keep GITLAB_TOKEN secure
- **Authentication**: Enable auth for shared environments

---

## Next Steps

1. **Index Your Data**
   - Import your code repositories
   - Index GitLab repositories
   - Import documentation

2. **Configure Your Client**
   - Choose VS Code, Claude Desktop, or Cursor
   - Add NeoFlow MCP configuration
   - Test the connection

3. **Start Using**
   - Try `ask_chat` with natural language questions
   - Explore specific search tools
   - Integrate into your workflow

4. **Optimize**
   - Tune search queries
   - Adjust timeouts if needed
   - Monitor performance

---

## Support

- **Documentation**: See `docs/` directory
- **Examples**: See `examples/` directory  
- **Issues**: Create GitHub issue
- **Discussions**: GitHub Discussions

---

## Resources

- **MCP Specification**: https://spec.modelcontextprotocol.io/
- **MCP Python SDK**: https://github.com/modelcontextprotocol/python-sdk
- **NeoFlow Documentation**: `docs/README.md`
- **Configuration Guide**: `docs/CONFIGURATION.md`
