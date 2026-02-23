# CLI Reference

Complete reference for NeoFlow command-line interface.

## Table of Contents

- [Overview](#overview)
- [Global Options](#global-options)
- [Commands](#commands)
- [Interactive Mode](#interactive-mode)
- [Environment Variables](#environment-variables)
- [Examples](#examples)

## Overview

NeoFlow provides a rich command-line interface for all operations. The CLI supports multiple modes of operation:

- **Interactive Mode**: Default mode with multi-turn conversation
- **Agent Mode**: Autonomous task execution with planning
- **Search Mode**: Direct search queries
- **Server Mode**: Start REST API, MCP server, or MCP proxy
- **Import Mode**: Data import and indexing

## Global Options

These options work with all commands:

```bash
neoflow [OPTIONS] [COMMAND] [ARGS]
```

### Options

| Option | Short | Description |
|--------|-------|-------------|
| `--verbose` | `-v` | Enable debug logging |
| `--info` | `-i` | Enable info logging |
| `--help` | `-h` | Show help message |
| `--version` | | Show version information |

## Commands

### Interactive Mode (Default)

Start interactive chat session.

```bash
neoflow
# or explicitly:
neoflow interactive
```

**Features:**
- Multi-turn conversation
- Context preservation across turns
- Access to all search tools
- Command shortcuts (see below)
- Session history

**Interactive Commands:**
- `/help` - Show available commands
- `/clear` - Clear conversation history
- `/history` - Show conversation history
- `/save <filename>` - Save conversation
- `/load <filename>` - Load conversation
- `/t=<template>` - Use a template
- `/quit` or `/exit` - Exit interactive mode
- `Ctrl+C` - Cancel current operation
- `Ctrl+D` - Exit

**Example:**
```bash
$ neoflow
NeoFlow Interactive Mode
Type /help for commands, Ctrl+D to exit

You: How do I implement JWT authentication?
Assistant: [searches and provides answer]

You: Show me example code
Assistant: [generates code example]
```

---

### Agent Mode

Execute autonomous tasks with planning and tool usage.

```bash
neoflow agent [OPTIONS] TASK
```

**Arguments:**
- `TASK` - Task description (required)

**Options:**
- `--no-planning` - Disable planning phase (execute directly)
- `--domain <name>` - Load domain-specific knowledge
- `--working-dir <path>` - Set working directory

**Domain References:**
Use `@domain_name` in task description to load specific knowledge:
```bash
neoflow agent "@react Create a login component with form validation"
```

**Features:**
- Multi-step task planning
- Autonomous tool usage
- File operations (read, write, create)
- Code execution
- Search capabilities
- Progress tracking
- Context optimization

**Example:**
```bash
# Simple task
neoflow agent "Fix the authentication bug in user_service.py"

# Complex task with planning
neoflow agent "Create a REST API with CRUD operations for users"

# With domain knowledge
neoflow agent "@python @fastapi Create an API endpoint for file upload"
```

---

### Search Mode

Execute search queries and get answers.

```bash
neoflow search [OPTIONS]
```

**Options:**
| Option | Short | Required | Description |
|--------|-------|----------|-------------|
| `--query <text>` | `-q` | No* | Search query |
| `--project <name>` | `-p` | No | Project filter |
| `--output <filename>` | `-o` | No | Save output to file |

*If not provided, prompts interactively.

**Search Types:**
- Code search (indexed repositories)
- Documentation search
- Ticket search
- Global workspace search

**Example:**
```bash
# Interactive search
neoflow search

# Direct query
neoflow search -q "How to configure CORS in FastAPI?"

# With project filter
neoflow search -q "authentication implementation" -p "backend"

# Save results
neoflow search -q "API documentation" -o api_docs
```

---

### Server Mode

Start NeoFlow server in one of three modes.

```bash
neoflow server --rest [OPTIONS]
neoflow server --mcp [OPTIONS]
neoflow server --proxy --remote-url <url> [OPTIONS]
```

**Options:**
| Option | Default | Description |
|--------|---------|-------------|
| `--rest` | Off | Run REST API server |
| `--mcp` | Off | Run MCP server |
| `--proxy` | Off | Run local MCP proxy (stdio → remote HTTP/SSE) |
| `--host <addr>` | `localhost` | REST bind address (`--rest`) |
| `--port <num>` | `9720` | REST port (`--rest`) |
| `--reload` | No | Enable auto-reload for REST (`--rest`) |
| `--transport <stdio\|sse>` | `stdio` | MCP transport (`--mcp`) |
| `--remote-url <url>` | None | Remote MCP URL (`--proxy`, required) |
| `--auth-token <token>` | None | Auth token for remote MCP (`--proxy`) |

**Example:**
```bash
# REST API (default settings)
neoflow server --rest

# Custom host and port
neoflow server --rest --host 0.0.0.0 --port 8000

# MCP server (stdio)
neoflow server --mcp

# MCP server (SSE)
neoflow server --mcp --transport sse

# MCP proxy to remote server
neoflow server --proxy --remote-url http://server.example.com:9721
```

**Server Endpoints:**
- `GET /` - API information
- `GET /docs` - Swagger UI
- `GET /redoc` - ReDoc documentation
- `GET /api/v1/health` - Health check
- `POST /api/v1/query` - Execute query
- `POST /api/v1/sessions` - Create session
- See [API Server](API_SERVER.md) for full API documentation

---

### Import Commands

Import data into Weaviate using a single command with mode options.

```bash
neoflow import [OPTIONS]
```

**Options:**
| Option | Description |
|--------|-------------|
| `--tickets` | Import ticket data |
| `--docs <path>` | Import documentation files from a directory |
| `--zip <file>` | Import code from a zip archive |
| `--source [path]` | Import code from a source folder (defaults to current directory if omitted) |
| `--name <repo>` | Repository label for code import (required with `--zip` or `--source`) |

**Example:**
```bash
# Import tickets
neoflow import --tickets

# Import documentation
neoflow import --docs ./docs

# Import code zip
neoflow import --zip ./repo.zip --name my-repo

# Import current folder source code
neoflow import --source --name my-repo

# Import source code from a specific folder
neoflow import --source ./path/to/repo --name my-repo
```

**Ticket Format:**
```json
{
  "reference": "TICKET-12345",
  "question": "How do I...",
  "metadata": {
    "title": "Issue Title",
    "url": "https://..."
  },
  "comments": [
    {"message": "Comment text"}
  ]
}
```

---

### Knowledge Pack Commands

Build, install, uninstall, and list Knowledge Packs.

```bash
neoflow knowledge-pack --build <path/to/content> [-o <output/folder>]
neoflow knowledge-pack --install <file.nkp>
neoflow knowledge-pack --uninstall <pack-name> [--keep-domain]
neoflow knowledge-pack --list
```

**Options:**
| Option | Description |
|--------|-------------|
| `--build` | Build a knowledge pack from a folder containing `manifest.json` |
| `--install` | Install a `.nkp` package |
| `--uninstall` | Uninstall by pack name (supports with/without `.nkp`) |
| `--list` | Show installed knowledge packs |
| `--keep-domain` | Keep copied domain files during uninstall |
| `-o, --output <path>` | Output directory for build artifacts |

**Behavior notes:**
- Build validates manifest metadata, sections, and referenced paths before packaging.
- Install shows metadata, asks confirmation, and imports docs/domain/tickets/code snippets.
- Uninstall removes Weaviate data by `pack-name`; domain files are removed unless `--keep-domain` is set.
- Manual imports can be removed with:

```bash
neoflow knowledge-pack --uninstall manual-import
```

For full manifest and lifecycle details, see [Knowledge Pack](KNOWLEDGE_PACK.md).

---

### Tool Pack Commands

Create, validate, build, install, uninstall, and list custom agent tool packs (`.ntp`).

```bash
neoflow tool new -n "My Tool Pack" [-o <parent-dir>] [--force]
neoflow tool validate <path/to/pack-source>
neoflow tool build <path/to/pack-source> [-o <output/folder>]
neoflow tool install <file.ntp>
neoflow tool uninstall <tag-or-name>
neoflow tool list
```

**Subcommands:**

| Subcommand | Description |
|------------|-------------|
| `new` | Scaffold a new tool-pack source directory with `manifest.json`, `tools/tool_definition.py`, and one starter tool |
| `validate` | Validate `manifest.json` fields and referenced tool files |
| `build` | Build a `.ntp` archive from a validated source directory |
| `install` | Install a `.ntp` package into `~/.neoflow/tools/<tag>/` |
| `uninstall` | Remove an installed tool pack by `tag` or `name` |
| `list` | Show all installed tool packs from `~/.neoflow/tool-pack.json` |

**Example workflow:**

```bash
# 1) Create scaffold
neoflow tool new -n "Workspace Utilities"

# 2) Implement your tool(s), then validate
neoflow tool validate workspace-utilities

# 3) Build package
neoflow tool build workspace-utilities

# 4) Install package
neoflow tool install workspace-utilities-v1.0.0.ntp

# 5) Confirm installation
neoflow tool list
```

**Runtime behavior:**
- Installed packs are loaded automatically when `neoflow agent ...` starts.
- Custom tool names cannot override built-in reserved actions.
- Tools marked `security_level = "unsafe"` load only when `AGENT_UNSAFE_MODE=true`.

For full manifest schema, tool contract, and sample packs, see [Tool Packs](tools/README.md).

---

### Database Commands

Manage Weaviate database collections.

#### Clear Collections

Delete Weaviate collections.

```bash
neoflow db clear [OPTIONS]
```

**Options:**
| Option | Description |
|--------|-------------|
| `--collection <name>` | Specific collection to clear (optional, clears all if omitted) |

**Features:**
- Safety confirmation prompt
- Lists collections before deletion
- Verifies Weaviate connectivity
- Provides clear success/error messages

**Examples:**
```bash
# Clear all collections
neoflow db clear

# Clear specific collection
neoflow db clear --collection Tickets
neoflow db clear --collection CodeSnippets
neoflow db clear --collection Documentation
```

**Common Collections:**
- `Tickets` - Support ticket data
- `Comments` - Ticket comments with references
- `CodeSnippets` - Indexed code from zipped repositories
- `Documentation` - Imported documentation files

**Output Example:**
```
Are you sure you want to delete ALL collections? [y/N]: y
Deleting 3 collection(s)...
✓ Deleted: Tickets
✓ Deleted: Comments
✓ Deleted: CodeSnippets
All collections cleared successfully.
```

**See also:** [Database Management Documentation](DB_COMMANDS.md)

---





### Status Commands

#### Health Check

Check service connectivity.

```bash
neoflow status [OPTIONS]
```

**Checks:**
- Weaviate connection
- Ollama/LLM provider availability

**Example:**
```bash
neoflow status
```

**Output:**
```
Service Status:
✓ Weaviate (localhost:8080)
✓ Ollama (http://ollama:11434)
```

---

### Configuration Commands

#### Show Configuration

Display current configuration.

```bash
neoflow config [OPTIONS]
```

**Options:**
| Option | Description |
|--------|-------------|
| `--show-secrets` | Include API tokens (use with caution) |
| `--format <type>` | Output format: `table`, `json`, `yaml` |

**Example:**
```bash
# Default table format
neoflow config

# JSON format
neoflow config --format json

# With secrets (be careful!)
neoflow config --show-secrets
```

#### Validate Configuration

```bash
neoflow config --validate
```

Validates configuration and reports issues.

---

### Template Commands

#### List Templates

```bash
neoflow templates [OPTIONS]
```

**Options:**
- `--path <dir>` - Templates directory (default: `~/.neoflow/templates/`)

**Example:**
```bash
neoflow templates
```

**Output:**
```
Available Templates:
  - sow: Statement of Work generator
  - status: Status report generator
```

#### Use Template

Templates can be used in interactive mode:

```bash
$ neoflow
You: /t=sow
[Template form appears]
```

Or directly:

```bash
neoflow template <name>
```

---

## Environment Variables

NeoFlow respects the following environment variables:

### Weaviate Configuration
```bash
WEAVIATE_HOST=localhost
WEAVIATE_PORT=8080
WEAVIATE_GRPC_HOST=
WEAVIATE_GRPC_PORT=50051
WEAVIATE_HTTP_SECURE=false
WEAVIATE_GRPC_SECURE=false
```

### Importer Configuration
```bash
IMPORTER_TICKETS_DIR=tickets
IMPORTER_BATCH_SIZE=300
IMPORTER_MAX_WORKERS=20
IMPORTER_MAX_FILE_SIZE_BYTES=1000000
```

### LLM Provider Configuration
```bash
# Provider selection
LLM_PROVIDER=ollama  # ollama, vllm, openai, auto

# Ollama
OLLAMA_API_URL=http://ollama:11434
OLLAMA_MODEL=qwen3-coder:latest

# vLLM
VLLM_API_URL=http://vllm:8000
VLLM_MODEL=meta-llama/Llama-2-13b-chat-hf

# OpenAI
OPENAI_API_KEY=sk-...
OPENAI_API_BASE=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
```

### Agent Configuration
```bash
# Enable/disable planning
AGENT_PLANNING_ENABLED=true

# Context management
AGENT_CONTEXT_TOKEN_THRESHOLD=25000
AGENT_LARGE_MESSAGE_RATIO=0.50
```

### Chat Configuration
```bash
CHAT_MAX_ITERATIONS=25
CHAT_SAVE_HISTORY=true
CHAT_HISTORY_DIR=chat_history
```

### Server Configuration
```bash
SERVER_HOST=localhost
SERVER_PORT=9720
SERVER_SESSION_TTL_MINUTES=60
SERVER_MAX_SESSIONS=100
```

---

## Examples

### Basic Workflows

#### 1. Quick Search
```bash
# Interactive
neoflow search

# Direct
neoflow search -q "How to implement caching?"
```

#### 2. Code Generation
```bash
neoflow agent "Create a Python function to validate email addresses"
```

#### 3. Complex Task
```bash
neoflow agent "Analyze user_service.py and suggest optimizations"
```

#### 4. Documentation
```bash
neoflow search -q "API authentication workflow" -o auth_docs
```

### Advanced Workflows

#### 1. Initial Setup
```bash
# Start services
docker compose up -d

# Import tickets
neoflow import --tickets


# Start interactive session
neoflow
```

#### 2. Development Workflow
```bash
# Start server in dev mode
neoflow server --rest --reload &

# Use agent for development
neoflow agent "Add input validation to the login endpoint"

# Test search
curl -X POST http://localhost:9720/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"query": "show validation examples"}'
```

#### 3. Maintenance
```bash
# Check status
neoflow status

# Validate configuration
neoflow config --validate
```

---

## Tips and Tricks

### 1. Verbose Mode for Debugging
```bash
neoflow -v agent "Your task"
```

### 2. Save All Search Results
Create alias in your `.bashrc`:
```bash
alias nfs='neoflow search -o $(date +%Y%m%d_%H%M%S)'
```

### 3. Project-Specific Configuration
Create `.neoflow/` directory in your project:
```bash
mkdir .neoflow
echo "Project-specific context" > .neoflow/README.md
```

### 4. Quick Template Access
In interactive mode:
```
You: /t=status
[Fill template form]
```

Templates are loaded from `~/.neoflow/templates/`. On first run, NeoFlow copies bundled defaults there.

### 5. Background Server
```bash
nohup neoflow server --rest > server.log 2>&1 &
```

---

## Troubleshooting

### Connection Issues

**Weaviate not reachable:**
```bash
# Check if running
docker ps | grep weaviate

# Restart
docker compose restart weaviate
```

**Ollama not reachable:**
```bash
# Check service
docker ps | grep ollama

# Test directly
curl http://localhost:11434/api/tags
```

### Performance Issues

**Slow searches:**
- Check Weaviate memory usage
- Consider increasing `chunk_size_bytes` in config
- Use more specific queries

**Out of memory:**
```bash
# Adjust context threshold
export AGENT_CONTEXT_TOKEN_THRESHOLD=15000
```

### Common Errors

**"Template not found":**
- Check `~/.neoflow/templates/` directory exists
- Verify template name (case-sensitive)
- Ensure `.yaml` extension in file

**"Collection does not exist":**
```bash
# Re-import data
neoflow import --tickets
```

---

## See Also

- [Agent System](AGENT_SYSTEM.md) - Agent mode details
- [Chat System](CHAT_SYSTEM.md) - Chat mode details
- [API Server](API_SERVER.md) - Server mode and API
- [Configuration](CONFIGURATION.md) - Configuration reference
- [Search Features](SEARCH_FEATURES.md) - Search capabilities
