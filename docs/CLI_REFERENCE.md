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
- **Server Mode**: Start REST API server
- **Import Mode**: Data import and indexing
- **GitLab Mode**: Repository management

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
- GitLab live search
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

Start REST API server.

```bash
neoflow serve [OPTIONS]
```

**Options:**
| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--host <addr>` | `-h` | `localhost` | Bind address |
| `--port <num>` | `-p` | `9720` | Port number |
| `--reload` | | No | Enable auto-reload (dev) |

**Example:**
```bash
# Default settings
neoflow serve

# Custom host and port
neoflow serve --host 0.0.0.0 --port 8000

# Development mode with reload
neoflow serve --reload
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

Import data into Weaviate.

#### Import Tickets

```bash
neoflow import [OPTIONS]
```

**Options:**
| Option | Description |
|--------|-------------|
| `--tickets-dir <path>` | Directory containing ticket JSON files (default: `tickets/`) |
| `--batch-size <num>` | Batch size for imports (default: 300) |

**Features:**
- Parallel processing
- Automatic chunking for large content
- Progress tracking
- Collection recreation (clears existing data)

**Example:**
```bash
# Default directory
neoflow import

# Custom directory
neoflow import --tickets-dir ./data/tickets

# Custom batch size
neoflow import --batch-size 500
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
- `CodeSnippets` - Indexed code from GitLab repositories
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

### GitLab Commands

Manage GitLab repository indexing.

#### Index Repositories

Index all configured repositories.

```bash
neoflow gitlab-index [OPTIONS]
```

**Prerequisites:**
- `GITLAB_TOKEN` environment variable must be set
- `gitlab_repos.yaml` configuration file

**Features:**
- Indexes all configured repositories
- Creates Code collection in Weaviate
- Extracts imports and definitions
- Detects and marks test files
- Smart code chunking with overlap
- Progress tracking

**Example:**
```bash
neoflow gitlab-index
```

#### Refresh Repository

Re-index a specific repository or all repositories.

```bash
neoflow gitlab-refresh [OPTIONS] [REPO]
```

**Arguments:**
- `REPO` - Repository name (optional, refreshes all if omitted)

**Features:**
- Incremental update
- Clears existing data for repository
- Maintains other repositories

**Example:**
```bash
# Refresh specific repo
neoflow gitlab-refresh backend-api

# Refresh all repos
neoflow gitlab-refresh
```

#### List Repositories

List all configured repositories.

```bash
neoflow gitlab-list
```

**Output:**
```
Configured GitLab Repositories:
  - backend-api (mygroup/backend-api)
  - frontend-app (mygroup/frontend-app)
  - shared-lib (mygroup/shared-lib)
```

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
- GitLab API connectivity (if configured)

**Example:**
```bash
neoflow status
```

**Output:**
```
Service Status:
✓ Weaviate (localhost:8080)
✓ Ollama (http://ollama:11434)
✓ GitLab API (configured)
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
- `--path <dir>` - Templates directory (default: `templates/`)

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
```

### GitLab Configuration
```bash
GITLAB_TOKEN=your_token_here
GITLAB_GROUP_PATH=YourGroup/
GITLAB_BASE_URL=https://gitlab.example.com/api/v4
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
neoflow import --tickets-dir ./data/tickets

# Index GitLab repos
export GITLAB_TOKEN=your_token
neoflow gitlab-index

# Start interactive session
neoflow
```

#### 2. Development Workflow
```bash
# Start server in dev mode
neoflow serve --reload &

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

# Refresh GitLab index
neoflow gitlab-refresh

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

### 5. Chain Commands
```bash
neoflow import && neoflow gitlab-index && neoflow serve
```

### 6. Background Server
```bash
nohup neoflow serve > server.log 2>&1 &
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
- Check `templates/` directory exists
- Verify template name (case-sensitive)
- Ensure `.yaml` extension in file

**"GITLAB_TOKEN not set":**
```bash
export GITLAB_TOKEN=your_token_here
```

**"Collection does not exist":**
```bash
# Re-import data
neoflow import
```

---

## See Also

- [Agent System](AGENT_SYSTEM.md) - Agent mode details
- [Chat System](CHAT_SYSTEM.md) - Chat mode details
- [API Server](API_SERVER.md) - Server mode and API
- [Configuration](CONFIGURATION.md) - Configuration reference
- [Search Features](SEARCH_FEATURES.md) - Search capabilities
