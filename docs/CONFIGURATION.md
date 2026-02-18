# Configuration Reference

Complete reference for all NeoFlow configuration options.

## Table of Contents

- [Overview](#overview)
- [Configuration Methods](#configuration-methods)
- [Configuration Sections](#configuration-sections)
- [Environment Variables](#environment-variables)
- [Examples](#examples)

## Overview

NeoFlow uses a dataclass-based configuration system with support for environment variable overrides. Configuration is centralized in [config.py](../neoflow/config.py).

## Configuration Methods

### 1. Environment Variables (Recommended)

```bash
export WEAVIATE_HOST=localhost
export GITLAB_TOKEN=your_token
export LLM_PROVIDER=ollama
```

### 2. .env File

```bash
# .env
WEAVIATE_HOST=localhost
WEAVIATE_PORT=8080
GITLAB_TOKEN=glpat-...
LLM_PROVIDER=ollama
```

Load with:
```python
from dotenv import load_dotenv
load_dotenv()
```

### 3. Code Configuration

```python
from neoflow.config import Config

config = Config.from_env()
config.weaviate.host = "custom_host"
config.gitlab.api_token = "custom_token"
```

### 4. Project-Local Configuration

Create `.neoflow/` directory:

```
project/
├── .neoflow/
│   ├── README.md          # Project context
│   ├── conventions.md     # Coding standards
│   └── architecture.md    # System design
└── ...
```

Agent automatically loads these files for context.

## Configuration Sections

### Weaviate Configuration

```python
@dataclass
class WeaviateConfig:
    host: str = "localhost"
    port: int = 8080
    timeout_init: int = 20
    timeout_query: int = 480
    timeout_insert: int = 120
```

**Environment Variables:**
```bash
WEAVIATE_HOST=localhost     # Weaviate hostname
WEAVIATE_PORT=8080          # Weaviate port
```

**Description:**
- `host`: Weaviate server hostname or IP
- `port`: Weaviate server port
- `timeout_init`: Connection timeout (seconds)
- `timeout_query`: Query timeout (seconds)
- `timeout_insert`: Insert timeout (seconds)

### Importer Configuration

```python
@dataclass
class ImporterConfig:
    tickets_dir: str = "tickets"
    batch_size: int = 300
    max_workers: int = 20
```

**Environment Variables:**
```bash
IMPORTER_TICKETS_DIR=tickets
IMPORTER_BATCH_SIZE=300
IMPORTER_MAX_WORKERS=20
```

**Description:**
- `tickets_dir`: Directory containing ticket JSON files
- `batch_size`: Number of records per batch insert
- `max_workers`: Parallel workers for processing

### GitLab Configuration

```python
@dataclass
class GitLabConfig:
    base_url: str = "https://gitlab.com/api/v4"
    api_token: str = ""
    gitlab_group_path: str = "mygroup/"
    max_file_size_bytes: int = 1_000_000  # 1MB
    repos_config_path: str = "gitlab_repos.yaml"
    allowed_extensions: tuple[str, ...] = (
        ".py", ".js", ".ts", ".java", ".go", ".md",
        ".yaml", ".yml", ".json", ".xml", ".sql",
    )
    live_search_keywords: tuple[str, ...] = (
        "gitlab:", "repository:", "repo:", "project:",
    )
```

**Environment Variables:**
```bash
GITLAB_BASE_URL=https://gitlab.com/api/v4
GITLAB_TOKEN=glpat-...
GITLAB_GROUP_PATH=MyOrg/
GITLAB_MAX_FILE_SIZE_BYTES=1000000
GITLAB_REPOS_CONFIG=gitlab_repos.yaml
```

**Description:**
- `base_url`: GitLab API endpoint
- `api_token`: Personal access token
- `gitlab_group_path`: Group path prefix
- `max_file_size_bytes`: Skip files larger than this
- `repos_config_path`: Repository configuration file
- `allowed_extensions`: File types to index
- `live_search_keywords`: Triggers for live GitLab search

### Agent Configuration

```python
@dataclass
class AgentConfig:
    context_token_threshold: int = 25_000
    large_message_ratio: float = 0.50
    planning_enabled: bool = True
```

**Environment Variables:**
```bash
AGENT_CONTEXT_TOKEN_THRESHOLD=25000
AGENT_LARGE_MESSAGE_RATIO=0.50
AGENT_PLANNING_ENABLED=true
```

**Description:**
- `context_token_threshold`: Max tokens before context optimization
- `large_message_ratio`: Ratio to determine "large" messages
- `planning_enabled`: Enable/disable planning phase

### Chat Configuration

```python
@dataclass
class ChatConfig:
    save_history: bool = True
    history_dir: str = "chat_history"
    max_iterations: int = 25
```

**Environment Variables:**
```bash
CHAT_SAVE_HISTORY=true
CHAT_HISTORY_DIR=chat_history
CHAT_MAX_ITERATIONS=25
```

**Description:**
- `save_history`: Save conversation history
- `history_dir`: Directory for history files
- `max_iterations`: Max tool calls per query

### LLM Provider Configuration

```python
@dataclass
class LLMProviderConfig:
    provider: str = "auto"  # 'auto', 'openai', 'vllm', 'ollama'
    openai_api_key: str = ""
    openai_api_base: str = ""
    openai_model: str = "gpt-4o-mini"
    vllm_api_url: str = "http://vllm:8000"
    vllm_model: str = "meta-llama/Llama-2-13b-chat-hf"
    ollama_api_url: str = "http://ollama:11434"
    ollama_model: str = "qwen3-coder:latest"
    embedding_model: str = "nomic-embed-text"
    chunk_size_bytes: int = 2_000
```

**Environment Variables:**
```bash
LLM_PROVIDER=auto
OPENAI_API_KEY=sk-...
OPENAI_API_BASE=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
VLLM_API_URL=http://vllm:8000
VLLM_MODEL=meta-llama/Llama-2-13b-chat-hf
OLLAMA_API_URL=http://ollama:11434
OLLAMA_MODEL=qwen3-coder:latest
EMBEDDING_MODEL=nomic-embed-text
CHUNK_SIZE_BYTES=2000
```

**Description:**
- `provider`: LLM provider selection
- `openai_*`: OpenAI configuration
- `vllm_*`: vLLM configuration
- `ollama_*`: Ollama configuration
- `embedding_model`: Model for embeddings
- `chunk_size_bytes`: Code chunk size

### Server Configuration

```python
@dataclass
class ServerConfig:
    host: str = "localhost"
    port: int = 9720
    cors_origins: list[str] = field(default_factory=lambda: ["*"])
    session_ttl_minutes: int = 60
    max_sessions: int = 100
```

**Environment Variables:**
```bash
SERVER_HOST=localhost
SERVER_PORT=9720
SERVER_CORS_ORIGINS=["*"]
SERVER_SESSION_TTL_MINUTES=60
SERVER_MAX_SESSIONS=100
```

**Description:**
- `host`: Server bind address
- `port`: Server port
- `cors_origins`: Allowed CORS origins
- `session_ttl_minutes`: Session lifetime
- `max_sessions`: Max concurrent sessions

### Main Configuration

```python
@dataclass
class Config:
    weaviate: WeaviateConfig = field(default_factory=WeaviateConfig)
    importer: ImporterConfig = field(default_factory=ImporterConfig)
    gitlab: GitLabConfig = field(default_factory=GitLabConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    chat: ChatConfig = field(default_factory=ChatConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    llm_provider: LLMProviderConfig = field(default_factory=LLMProviderConfig)
    reports_dir: str = "reports"
```

**Environment Variables:**
```bash
REPORTS_DIR=reports
```

## Environment Variables

Complete list of all environment variables:

### Weaviate
```bash
WEAVIATE_HOST=localhost
WEAVIATE_PORT=8080
```

### GitLab
```bash
GITLAB_BASE_URL=https://gitlab.com/api/v4
GITLAB_TOKEN=glpat-...
GITLAB_GROUP_PATH=MyOrg/
GITLAB_MAX_FILE_SIZE_BYTES=1000000
GITLAB_REPOS_CONFIG=gitlab_repos.yaml
```

### LLM Provider
```bash
LLM_PROVIDER=auto
OPENAI_API_KEY=sk-...
OPENAI_API_BASE=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
VLLM_API_URL=http://vllm:8000
VLLM_MODEL=meta-llama/Llama-2-13b-chat-hf
OLLAMA_API_URL=http://ollama:11434
OLLAMA_MODEL=qwen3-coder:latest
EMBEDDING_MODEL=nomic-embed-text
CHUNK_SIZE_BYTES=2000
```

### Agent
```bash
AGENT_CONTEXT_TOKEN_THRESHOLD=25000
AGENT_LARGE_MESSAGE_RATIO=0.50
AGENT_PLANNING_ENABLED=true
```

### Chat
```bash
CHAT_SAVE_HISTORY=true
CHAT_HISTORY_DIR=chat_history
CHAT_MAX_ITERATIONS=25
```

### Server
```bash
SERVER_HOST=localhost
SERVER_PORT=9720
SERVER_CORS_ORIGINS=["*"]
SERVER_SESSION_TTL_MINUTES=60
SERVER_MAX_SESSIONS=100
```

### Importer
```bash
IMPORTER_TICKETS_DIR=tickets
IMPORTER_BATCH_SIZE=300
IMPORTER_MAX_WORKERS=20
```

### Other
```bash
REPORTS_DIR=reports
```

## Examples

### Example 1: Local Development

```bash
# .env
WEAVIATE_HOST=localhost
WEAVIATE_PORT=8080

LLM_PROVIDER=ollama
OLLAMA_API_URL=http://localhost:11434
OLLAMA_MODEL=qwen3-coder:latest

GITLAB_TOKEN=glpat-local-dev-token

CHAT_SAVE_HISTORY=true
AGENT_PLANNING_ENABLED=true
```

### Example 2: Production Deployment

```bash
# .env
WEAVIATE_HOST=weaviate.prod.example.com
WEAVIATE_PORT=443

LLM_PROVIDER=vllm
VLLM_API_URL=http://vllm-cluster:8000
VLLM_MODEL=meta-llama/Llama-2-13b-chat-hf

GITLAB_BASE_URL=https://gitlab.example.com/api/v4
GITLAB_TOKEN=glpat-prod-token
GITLAB_GROUP_PATH=Engineering/

SERVER_HOST=0.0.0.0
SERVER_PORT=9720
SERVER_CORS_ORIGINS=["https://app.example.com"]
SERVER_SESSION_TTL_MINUTES=30
SERVER_MAX_SESSIONS=1000

CHAT_MAX_ITERATIONS=15
AGENT_CONTEXT_TOKEN_THRESHOLD=20000
```

### Example 3: OpenAI Setup

```bash
# .env
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-proj-...
OPENAI_MODEL=gpt-4o-mini

# Rest defaults
WEAVIATE_HOST=localhost
WEAVIATE_PORT=8080
```

### Example 4: Docker Compose

```bash
# .env for docker-compose.yaml
WEAVIATE_HOST=weaviate
WEAVIATE_PORT=8080

OLLAMA_API_URL=http://ollama:11434
OLLAMA_MODEL=qwen3-coder:latest

GITLAB_TOKEN=${GITLAB_TOKEN}  # From shell
```

### Example 5: Kubernetes

```yaml
# ConfigMap
apiVersion: v1
kind: ConfigMap
metadata:
  name: neoflow-config
data:
  WEAVIATE_HOST: "weaviate-service"
  WEAVIATE_PORT: "8080"
  LLM_PROVIDER: "vllm"
  VLLM_API_URL: "http://vllm-service:8000"
  SERVER_HOST: "0.0.0.0"
  SERVER_PORT: "9720"
---
# Secret
apiVersion: v1
kind: Secret
metadata:
  name: neoflow-secrets
stringData:
  GITLAB_TOKEN: "glpat-..."
  OPENAI_API_KEY: "sk-..."
```

## Validation

### Check Configuration

```bash
neoflow config
```

### Validate Settings

```bash
neoflow config --validate
```

### Show Secrets (Caution!)

```bash
neoflow config --show-secrets
```

### Export as JSON

```bash
neoflow config --format json > config.json
```

## Best Practices

### 1. Use Environment Variables

Prefer environment variables over hardcoding:

```python
# Good
config = Config.from_env()

# Avoid
config = Config()
config.gitlab.api_token = "hardcoded-token"
```

### 2. Separate Dev/Prod Configs

```bash
# .env.development
OLLAMA_MODEL=qwen3-coder:latest
CHAT_MAX_ITERATIONS=25

# .env.production
VLLM_MODEL=meta-llama/Llama-2-13b-chat-hf
CHAT_MAX_ITERATIONS=15
```

Load appropriate file:
```bash
cp .env.production .env
```

### 3. Never Commit Secrets

Add to `.gitignore`:
```
.env
.env.*
!.env.example
```

### 4. Use .env.example

```bash
# .env.example
WEAVIATE_HOST=localhost
GITLAB_TOKEN=your_token_here
LLM_PROVIDER=ollama
```

### 5. Validate on Startup

```python
config = Config.from_env()

# Validate critical settings
assert config.weaviate.host, "WEAVIATE_HOST required"
if config.gitlab.api_token:
    assert config.gitlab.api_token.startswith("glpat-"), "Invalid GitLab token"
```

## See Also

- [LLM Providers](LLM_PROVIDERS.md)
- [GitLab Integration](GITLAB_INTEGRATION.md)
- [CLI Reference](CLI_REFERENCE.md)
- [Deployment](DEPLOYMENT.md)
