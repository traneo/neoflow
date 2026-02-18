# NeoFlow Documentation

Welcome to the NeoFlow documentation! This directory contains comprehensive guides for all features and functionality.

## Getting Started

- **[Overview](OVERVIEW.md)** - Start here! Introduction, architecture, and quick start guide
- **[CLI Reference](CLI_REFERENCE.md)** - Complete command-line interface documentation

## Core Features

### Interactive Systems
- **[Chat System](CHAT_SYSTEM.md)** - Multi-turn conversations and search-based Q&A
- **[Agent System](AGENT_SYSTEM.md)** - Autonomous task execution with planning
- **[Loop Detection](LOOP_DETECTION.md)** - Preventing and resolving infinite loops in agent execution
- **[Template System](TEMPLATE_SYSTEM.md)** - Reusable query templates

### Search & Data
- **[Search Features](SEARCH_FEATURES.md)** - Semantic and hybrid search capabilities
- **[GitLab Integration](GITLAB_INTEGRATION.md)** - Repository indexing and code search
- **[Data Import](DATA_IMPORT.md)** - Ticket and document import system
- **[Database Management](DB_COMMANDS.md)** - Database collection management

### Backend & Configuration
- **[API Server](API_SERVER.md)** - REST API documentation and usage
- **[LLM Providers](LLM_PROVIDERS.md)** - Multi-provider LLM support (Ollama/vLLM/OpenAI)
- **[Configuration](CONFIGURATION.md)** - Complete configuration reference

## Quick Links

### Common Tasks

| Task | Documentation |
|------|--------------|
| Install and setup | [Overview - Getting Started](OVERVIEW.md#getting-started) |
| Run a search | [CLI Reference - Search Mode](CLI_REFERENCE.md#search-mode) |
| Execute a task | [Agent System](AGENT_SYSTEM.md) |
| Start the API server | [API Server](API_SERVER.md) |
| Index GitLab repos | [GitLab Integration](GITLAB_INTEGRATION.md) |
| Configure LLM provider | [LLM Providers](LLM_PROVIDERS.md) |
| Create templates | [Template System](TEMPLATE_SYSTEM.md) |
| Import ticket data | [Data Import](DATA_IMPORT.md) |
| Clear database collections | [Database Management](DB_COMMANDS.md) |

### Reference

| Topic | Documentation |
|-------|--------------|
| All CLI commands | [CLI Reference](CLI_REFERENCE.md) |
| Environment variables | [Configuration - Environment Variables](CONFIGURATION.md#environment-variables) |
| API endpoints | [API Server - Endpoints](API_SERVER.md#endpoints) |
| Search tools | [Search Features - Search Tools](SEARCH_FEATURES.md#search-tools) |
| Agent tools | [Agent System - Available Tools](AGENT_SYSTEM.md#available-tools) |

## Documentation Structure

```
docs/
├── README.md                    # This file
├── OVERVIEW.md                  # Project overview and architecture
├── CLI_REFERENCE.md             # Complete CLI documentation
├── CHAT_SYSTEM.md               # Chat mode documentation
├── AGENT_SYSTEM.md              # Agent mode documentation
├── API_SERVER.md                # REST API documentation
├── SEARCH_FEATURES.md           # Search capabilities
├── GITLAB_INTEGRATION.md        # GitLab integration guide
├── DATA_IMPORT.md               # Data import guide
├── DB_COMMANDS.md               # Database management commands
├── LLM_PROVIDERS.md             # LLM provider documentation
├── CONFIGURATION.md             # Configuration reference
├── TEMPLATE_SYSTEM.md           # Template system guide
├── LOOP_DETECTION.md            # Agent loop detection
└── VLLM_SETUP.md                # vLLM setup guide
```

## Features Overview

### 🤖 Agent System
Autonomous task execution with multi-step planning. Perfect for:
- Code generation and modification
- Bug fixing and refactoring
- Documentation creation
- Complex multi-file changes

[Read Agent System docs →](AGENT_SYSTEM.md)

### 💬 Chat System
Interactive conversations with search integration. Great for:
- Exploring codebases
- Finding solutions
- Research and learning
- Quick Q&A

[Read Chat System docs →](CHAT_SYSTEM.md)

### 🔍 Search Features
Powerful semantic search across:
- Code repositories (GitLab)
- Documentation
- Support tickets
- Workspace files

[Read Search Features docs →](SEARCH_FEATURES.md)

### 🔌 REST API
Production-ready HTTP API with:
- Stateless queries
- Session management
- Template execution
- Health monitoring

[Read API Server docs →](API_SERVER.md)

### 🦊 GitLab Integration
Seamless repository indexing:
- Automatic code indexing
- Smart chunking
- Metadata extraction
- Live search fallback

[Read GitLab Integration docs →](GITLAB_INTEGRATION.md)

### 🧠 Multi-Provider LLM
Flexible backend support:
- **Ollama**: Local, private, free
- **vLLM**: High-performance inference
- **OpenAI**: Cloud, state-of-the-art

[Read LLM Providers docs →](LLM_PROVIDERS.md)

### 📝 Template System
Reusable query patterns:
- Standardized workflows
- Form-based input
- YAML configuration
- Easy customization

[Read Template System docs →](TEMPLATE_SYSTEM.md)

## Examples & Tutorials

### Quick Start Examples

**Run a search:**
```bash
neoflow search -q "How to implement JWT authentication?"
```

**Execute a task:**
```bash
neoflow agent "Create a REST API endpoint for user registration"
```

**Start interactive chat:**
```bash
neoflow
You: How do I configure CORS in FastAPI?
```

**Start API server:**
```bash
neoflow serve
```

### Common Workflows

**1. Initial Setup**
```bash
# Start services
docker compose up -d

# Import data
neoflow import

# Index repositories
export GITLAB_TOKEN=your_token
neoflow gitlab-index

# Start using
neoflow
```

**2. Development Workflow**
```bash
# Search for implementation
neoflow search -q "authentication implementation"

# Generate code
neoflow agent "Add JWT middleware to API"

# Create documentation
neoflow agent "Document the authentication flow"
```

**3. API Integration**
```bash
# Start server
neoflow serve &

# Query from code
curl -X POST http://localhost:9720/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Show me error handling examples"}'
```

## Configuration

### Essential Environment Variables

```bash
# Weaviate
export WEAVIATE_HOST=localhost
export WEAVIATE_PORT=8080

# GitLab
export GITLAB_TOKEN=glpat-your_token_here

# LLM Provider (choose one)
export LLM_PROVIDER=ollama
# or
export LLM_PROVIDER=openai
export OPENAI_API_KEY=sk-your_key_here
```

[See full configuration reference →](CONFIGURATION.md)

## Troubleshooting

### Common Issues

**Services not reachable:**
```bash
# Check services
docker ps

# Restart if needed
docker compose restart
```

**Import fails:**
```bash
# Check Weaviate
docker logs neoflow-weaviate-1

# Verify JSON files
python -m json.tool tickets/ticket_10001.json
```

**GitLab indexing fails:**
```bash
# Verify token
echo $GITLAB_TOKEN

# Test API access
curl -H "PRIVATE-TOKEN: $GITLAB_TOKEN" \
  https://gitlab.com/api/v4/user
```

**LLM provider issues:**
```bash
# Check Ollama
curl http://localhost:11434/api/tags

# Check vLLM
curl http://localhost:8000/v1/models

# Check OpenAI
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY"
```

### Getting Help

Each documentation file includes a troubleshooting section:
- [Chat System Troubleshooting](CHAT_SYSTEM.md#troubleshooting)
- [Agent System Troubleshooting](AGENT_SYSTEM.md#troubleshooting)
- [Search Features Troubleshooting](SEARCH_FEATURES.md#troubleshooting)
- [GitLab Integration Troubleshooting](GITLAB_INTEGRATION.md#troubleshooting)
- [Data Import Troubleshooting](DATA_IMPORT.md#troubleshooting)
- [LLM Providers Troubleshooting](LLM_PROVIDERS.md#troubleshooting)

## Additional Resources

- **Main README**: [../README.md](../README.md)
- **License**: [../LICENSE](../LICENSE)

## Version

Documentation for NeoFlow v0.0.21

Last updated: February 17, 2026

---

**Need help?** Start with the [Overview](OVERVIEW.md) or jump to a specific feature guide above.
