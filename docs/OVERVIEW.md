# NeoFlow Documentation

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Key Features](#key-features)
- [Getting Started](#getting-started)
- [Tool Packs Quick Start](#tool-packs-quick-start)
- [Documentation Index](#documentation-index)

## Overview


The system is designed to help developers with:
- **Code Generation & Analysis**: Generate code snippets and full implementations from natural language
- **Documentation Management**: Create and maintain project documentation with AI assistance
- **Testing Support**: Generate test cases and assist with test automation
- **Project Management**: Organize and manage development tasks intelligently
- **Code Search**: Perform semantic and hybrid searches across codebases

## Architecture

NeoFlow is built on a modular architecture with the following key components:

```
┌─────────────────────────────────────────────────────────────┐
│                        NeoFlow CLI                           │
│                    (Interactive Interface)                   │
└───────────┬─────────────────────────────────────────────────┘
            │
    ┌───────┴────────┐
    │                │
┌───▼───┐      ┌────▼────┐
│ Agent │      │  Chat   │
│ Mode  │      │  Mode   │
└───┬───┘      └────┬────┘
    │               │
    └───────┬───────┘
            │
    ┌───────▼────────┐
    │  LLM Providers │
    │ (Ollama/vLLM/  │
    │    OpenAI)     │
    └───────┬────────┘
            │
┌───────────┴──────────────┐
│   Search & Indexing      │
│  ┌────────────────────┐  │
│  │ Weaviate Vector DB │  │
│  └────────────────────┘  │
│  ┌────────────────────┐  │
│  │  Ticket Importer   │  │
│  └────────────────────┘  │
└──────────────────────────┘
```

### Core Components

1. **CLI Interface** - Command-line interface for all interactions
2. **Agent System** - Autonomous task execution with planning and tool use
3. **Chat System** - Multi-turn conversational interface with search tools
4. **REST API** - HTTP API for programmatic access and integrations
5. **Search Engine** - Semantic and hybrid search across multiple data sources
6. **LLM Providers** - Pluggable backend support (Ollama, vLLM, OpenAI)
7. **Vector Database** - Weaviate for semantic search and retrieval
9. **Data Importers** - Ticket and documentation import systems

## Key Features

### 1. Agent Mode
Autonomous task execution with:
- Multi-step planning and execution
- Tool usage (file operations, search, code execution)
- Context optimization for large projects
- Domain-specific knowledge loading
- Task tracking and resolution

### 2. Chat Mode
Interactive conversation with:
- Multi-turn context maintenance
- Search tool integration
- Iterative refinement
- Session history management
- Configurable iteration limits

### 3. Search Capabilities
Powerful search across:
- Documentation
- Support tickets
- Global workspace search
- File system operations

### 4. REST API Server
Production-ready API with:
- Stateless query endpoints
- Session-based chat
- Template management
- Health monitoring
- CORS support
- Session cleanup

### 6. Template System
Reusable query templates:
- YAML-based configuration
- Interactive forms
- Variable substitution
- Quick access via `/t=<name>`

### 7. Multi-Provider LLM Support
Flexible LLM backends:
- **Ollama**: Local deployment, privacy-focused
- **vLLM**: High-performance inference
- **OpenAI**: Cloud-based, state-of-the-art models
- Auto-detection and fallback
- Unified configuration

## Getting Started

### Prerequisites

- Python 3.12 or higher
- Docker and Docker Compose
- GPU with CUDA support (recommended)

### Quick Start

1. **Install NeoFlow**
   ```bash
   git clone https://github.com/your-org/neoflow.git
   cd neoflow
   pip install -e .
   ```

2. **Start Services**
   ```bash
   docker compose up -d
   ```

3. **Run Interactive Mode**
   ```bash
   neoflow
   ```

4. **Try a Search**
   ```bash
   neoflow search -q "How do I implement authentication?"
   ```

5. **Start Agent Mode**
   ```bash
   neoflow agent "Create a REST API endpoint for user registration"
   ```

### Configuration

NeoFlow uses environment variables and defaults from [config.py](../neoflow/config.py):

```bash
# Weaviate connection
export WEAVIATE_HOST=localhost
export WEAVIATE_PORT=8080
export WEAVIATE_GRPC_HOST=
export WEAVIATE_GRPC_PORT=50051
export WEAVIATE_HTTP_SECURE=false
export WEAVIATE_GRPC_SECURE=false


# LLM provider selection
export LLM_PROVIDER=ollama  # or vllm, openai, auto
export OLLAMA_MODEL=qwen3-coder:latest
```

See [Configuration Guide](CONFIGURATION.md) for detailed options.

## Tool Packs Quick Start

Create, package, and install custom agent tools in minutes:

```bash
# 1) Scaffold a new pack source
neoflow tool new -n "Workspace Utilities"

# 2) Implement tools, then validate
neoflow tool validate workspace-utilities

# 3) Build package
neoflow tool build workspace-utilities

# 4) Install package
neoflow tool install workspace-utilities-v1.0.0.ntp

# 5) Verify installation
neoflow tool list
```

Installed tools are loaded automatically when you run `neoflow agent ...`.
For manifest schema, security rules, and complete examples, see [Tool Packs](tools/README.md).

## Documentation Index

### Core Features
- [CLI Reference](CLI_REFERENCE.md) - Complete command-line interface documentation
- [Agent System](AGENT_SYSTEM.md) - Autonomous task execution and planning
- [Chat System](CHAT_SYSTEM.md) - Interactive conversation interface
- [Template System](TEMPLATE_SYSTEM.md) - Reusable query templates

### Search & Data
- [Search Features](SEARCH_FEATURES.md) - Semantic and hybrid search capabilities
- [Data Import](DATA_IMPORT.md) - Ticket and document import system

### Backend & Integration
- [REST API Server](API_SERVER.md) - HTTP API documentation
- [LLM Providers](LLM_PROVIDERS.md) - Multi-backend LLM support
- [Configuration](CONFIGURATION.md) - Complete configuration reference

### Advanced Topics
- [Context Optimization](CONTEXT_OPTIMIZATION.md) - Managing large contexts
- [Deployment](DEPLOYMENT.md) - Production deployment guide
- [Troubleshooting](TROUBLESHOOTING.md) - Common issues and solutions

## Architecture Decisions

### Why Weaviate?
- Native vector storage and search
- Hybrid search (keyword + semantic)
- Scalable and production-ready
- Good Python client library

### Why Multiple LLM Providers?
- Flexibility for different deployment scenarios
- Local development with Ollama
- Production performance with vLLM
- Cloud option with OpenAI
- Easy migration between providers

### Why Agent + Chat Modes?
- **Agent Mode**: For complex, multi-step tasks requiring autonomy
- **Chat Mode**: For interactive exploration and quick queries
- Different use cases require different interaction patterns

## Performance Considerations

- **Token Management**: Automatic context optimization to stay within limits
- **Batch Processing**: Parallel processing for imports and indexing
- **Caching**: Strategic caching of search results and embeddings
- **Chunking**: Smart code chunking with overlap for context preservation
- **Cleanup**: Automatic session cleanup in server mode

## Security Notes

- API tokens should be stored in environment variables
- Session data is cleaned up automatically
- File operations are validated for path traversal
- CORS can be configured for API access
- No credentials are logged by default

## Next Steps

- Read the [CLI Reference](CLI_REFERENCE.md) to learn all available commands
- Explore [Agent System](AGENT_SYSTEM.md) for autonomous task execution
- Review [Configuration](CONFIGURATION.md) for customization options
- See [API Server](API_SERVER.md) for programmatic access

## Support

- Documentation: [docs/](.)
- Issues: GitHub Issues
- License: [LICENSE](../LICENSE)
