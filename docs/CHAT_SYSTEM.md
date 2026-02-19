# Chat System

Comprehensive guide to NeoFlow's chat system for interactive queries and multi-turn conversations.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Features](#features)
- [Usage](#usage)
- [Available Tools](#available-tools)
- [Configuration](#configuration)
- [Advanced Topics](#advanced-topics)
- [Examples](#examples)

## Overview

The Chat System provides an interactive, tool-augmented conversation interface for querying and exploring your codebase, documentation, and support tickets. It uses a constrained agent loop that focuses on search and retrieval operations.

### Key Characteristics

- **Tool-Based**: Uses specific search tools rather than arbitrary code execution
- **Iterative**: Multiple rounds of tool usage to refine answers
- **Context-Aware**: Maintains conversation history across turns
- **Self-Validating**: Validates tool results before providing final answers
- **Safe**: Limited to search operations (no file writes or code execution)

### Use Cases

- Exploring codebases and documentation
- Finding relevant tickets and solutions
- Answering technical questions
- Researching implementation patterns
- Quick information retrieval
- Code examples and usage patterns

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                   Chat Interface                      │
│          (CLI Interactive or API Endpoint)            │
└─────────────────────┬────────────────────────────────┘
                      │
                      ▼
┌──────────────────────────────────────────────────────┐
│                  Chat Loop (chat.py)                  │
│  ┌─────────────────────────────────────────────┐    │
│  │  System Prompt + Conversation History        │    │
│  └─────────────────────────────────────────────┘    │
│                      │                                │
│                      ▼                                │
│  ┌─────────────────────────────────────────────┐    │
│  │          LLM Provider (Ollama/vLLM/         │    │
│  │              OpenAI)                         │    │
│  └─────────────────────────────────────────────┘    │
│                      │                                │
│                      ▼                                │
│  ┌─────────────────────────────────────────────┐    │
│  │     Parse Action (JSON Tool Call)           │    │
│  └─────────────────────────────────────────────┘    │
│                      │                                │
│          ┌───────────┴──────────────┐               │
│          ▼                           ▼               │
│  ┌──────────────┐           ┌──────────────┐       │
│  │ Execute Tool │           │     Done     │       │
│  │   (Search)   │           │ (Final Answer)│       │
│  └──────┬───────┘           └──────────────┘       │
│         │                                            │
│         └─────► Add to History ───► Loop            │
└──────────────────────────────────────────────────────┘
                      │
                      ▼
┌──────────────────────────────────────────────────────┐
│              Search Tools (tools.py)                  │
│  ┌────────────┬────────────┬─────────────────────┐  │
│  │ search_code│ search_docs│ search_tickets      │  │
│  ├────────────┴────────────┴─────────────────────┤  │
│  │         gitlab_live_search                     │  │
│  └────────────────────────────────────────────────┘  │
└─────────────────────┬────────────────────────────────┘
                      │
                      ▼
┌──────────────────────────────────────────────────────┐
│              Weaviate Vector Database                 │
│     (Code, Documentation, Tickets collections)        │
└──────────────────────────────────────────────────────┘
```

## Features

### 1. Multi-Turn Conversations

Maintains context across multiple interactions:

```
You: What authentication methods are available?
Assistant: [searches docs] We support JWT, OAuth2, and API keys...

You: Show me a JWT example
Assistant: [searches code] Here's an implementation from auth_service.py...
```

### 2. Tool-Based Search

Uses structured tools instead of free-form responses:

```json
{
  "action": "search_code",
  "query": "JWT authentication implementation",
  "limit": 5
}
```

### 3. Context Optimization

Automatically manages context to stay within token limits:
- Removes metadata from messages
- Summarizes old messages when context is large
- Preserves recent and important messages

### 4. Self-Validation

Validates results before providing final answer:
- Checks if search results are relevant
- Uses additional tools if needed
- Iterates until confident or max iterations reached

### 5. Source Tracking

Tracks all sources used in generating the answer:
```
Sources:
 - Code: backend/auth_service.py
 - Documentation: docs/authentication.md
 - Ticket: SUPPORT-12345
```

### 6. Cancellation Support

User can cancel long-running operations with `Ctrl+C`.

## Usage

### Interactive Mode

Start interactive chat:

```bash
neoflow
```

**Commands:**
- Type your question and press Enter
- `/help` - Show available commands
- `/clear` - Clear conversation history
- `/history` - Show conversation
- `/save <filename>` - Save conversation
- `/t=<template>` - Use template
- `Ctrl+C` - Cancel current operation
- `Ctrl+D` - Exit

### Programmatic Usage

```python
from neoflow.chat import run_chat
from neoflow.config import Config
from rich.console import Console
from neoflow.status_bar import StatusBar

config = Config.from_env()
console = Console()
bar = StatusBar()
bar.start()

answer = run_chat(
    query="How do I implement JWT authentication?",
    config=config,
    console=console,
    bar=bar,
    silent=False
)

bar.stop()
print(answer)
```

### REST API

```bash
curl -X POST http://localhost:9720/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "How to implement authentication?",
    "session_id": "optional-session-id"
  }'
```

## Available Tools

The chat system has access to the following tools:

### 1. search_code

Search indexed code repositories.

```json
{
  "action": "search_code",
  "query": "authentication implementation",
  "limit": 5
}
```

**Parameters:**
- `query`: Search query (required)
- `limit`: Max results (default: 5)

**Returns:**
- File paths, line numbers, code snippets
- Import statements, definitions
- Relevance scores

### 2. search_documentation

Search documentation content.

```json
{
  "action": "search_documentation",
  "query": "API authentication guide",
  "limit": 3
}
```

### 3. search_tickets

Search support tickets and comments.

```json
{
  "action": "search_tickets",
  "query": "login error 401",
  "limit": 3
}
```

### 4. get_full_ticket

Retrieve complete ticket details including ALL comments.

```json
{
  "action": "get_full_ticket",
  "reference": "TICKET-10234"
}
```

**Parameters:**
- `reference`: Ticket reference ID (e.g., 'SDK-10007', 'TICKET-12345')

**Returns:**
- Complete ticket details with title and URL
- Full question/description
- All comments in chronological order
- Formatted output for easy reading

**Usage:** Always use this after finding relevant tickets via `search_tickets` to see the complete conversation and context.

### 5. gitlab_live_search

Search GitLab repositories directly (not indexed).

```json
{
  "action": "gitlab_live_search",
  "query": "authentication handler config",
  "repository": "backend-api",
  "limit": 10
}
```

### 6. done

Signal completion with final answer.

```json
{
  "action": "done",
  "answer": "Based on the search results..."
}
```

## Configuration

```python
@dataclass
class ChatConfig:
    save_history: bool = True
    history_dir: str = "chat_history"
    max_iterations: int = 25
```

### Environment Variables

```bash
CHAT_MAX_ITERATIONS=25
CHAT_SAVE_HISTORY=true
CHAT_HISTORY_DIR=chat_history
```

## Examples

### Simple Query

```
You: How do I configure CORS in FastAPI?
Assistant: [Searches docs and code]

To configure CORS in FastAPI:
1. Import CORSMiddleware
2. Add middleware to your app
[code example]

Sources:
 - docs/fastapi_guide.md
 - backend/api/server.py
```

### Multi-Turn Conversation

```
You: What authentication methods do we support?
Assistant: We support JWT, OAuth2, and API keys...

You: Show me the JWT implementation
Assistant: [Reads auth_service.py] Here's the code...

You: Are there any known issues?
Assistant: [Searches tickets] Yes, TICKET-10234...
```

## See Also

- [CLI Reference](CLI_REFERENCE.md)
- [Search Features](SEARCH_FEATURES.md)
- [Configuration](CONFIGURATION.md)
