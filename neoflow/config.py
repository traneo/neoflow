import os
from dataclasses import dataclass, field


@dataclass
class WeaviateConfig:
    host: str = "localhost"
    port: int = 8080
    timeout_init: int = 20
    timeout_query: int = 480
    timeout_insert: int = 120


@dataclass
class ImporterConfig:
    tickets_dir: str = "tickets"
    batch_size: int = 300
    max_workers: int = 20
    max_file_size_bytes: int = 1_000_000  # 1MB


@dataclass
class AgentConfig:
    context_token_threshold: int =29_000
    large_message_ratio: float = 0.90
    planning_enabled: bool = True
    # Loop detection settings
    max_iterations: int = 200
    loop_detection_enabled: bool = True
    loop_action_window_size: int = 20
    loop_repetition_threshold: int = 8
    loop_error_threshold: int = 8
    loop_pattern_length: int = 10
    # Dictionary compression settings
    compression_enabled: bool = True
    compression_min_tokens: int = 1000  # Minimum tokens to trigger compression
    compression_min_chars: int = 5000   # Minimum characters to trigger compression
    # Command execution settings
    unsafe_mode: bool = False  # When True, bypasses run_command approvals and uses shell=True


@dataclass
class ChatConfig:
    save_history: bool = True
    history_dir: str = "chat_history"
    max_iterations: int = 25


@dataclass
class LLMProviderConfig:
    """Unified configuration for LLM and Weaviate providers.
    
    One provider setting controls both LLM operations and Weaviate
    vector/generative models. Simplifies deployment and provider switching.
    """
    provider: str = "auto"  # 'auto', 'openai', 'vllm', 'ollama'
    openai_api_key: str = ""
    openai_api_base: str = ""
    openai_model: str = "gpt-4o-mini"
    vllm_api_url: str = "http://vllm:8000"
    vllm_model: str = "meta-llama/Llama-2-13b-chat-hf"
    ollama_api_url: str = "http://ollama:11434"
    ollama_model: str = "glm-4.7-flash"
    embedding_model: str = "nomic-embed-text"
    chunk_size_bytes: int = 2_000


@dataclass
class ServerConfig:
    host: str = "localhost"
    port: int = 9720
    cors_origins: list[str] = field(default_factory=lambda: ["*"])
    session_ttl_minutes: int = 60
    max_sessions: int = 100
    enforce_system_prompt: bool = True
    api_key: str = ""
    api_key: str = ""


@dataclass
class MCPConfig:
    """Configuration for Model Context Protocol (MCP) server."""
    enabled: bool = True
    transport: str = "stdio"  # "stdio" or "sse"
    sse_host: str = "localhost"
    sse_port: int = 9721
    max_results_limit: int = 20
    timeout_seconds: int = 30
    auth_required: bool = False
    auth_token: str = ""


@dataclass
class Config:
    weaviate: WeaviateConfig = field(default_factory=WeaviateConfig)
    importer: ImporterConfig = field(default_factory=ImporterConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    chat: ChatConfig = field(default_factory=ChatConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    mcp: MCPConfig = field(default_factory=MCPConfig)
    llm_provider: LLMProviderConfig = field(default_factory=LLMProviderConfig)
    reports_dir: str = "reports"

    @classmethod
    def generate_env_template(cls) -> str:
        """Generate a complete .env template with all configuration options."""
        return """# ===================================================================
# NeoFlow Configuration Template
# ===================================================================
#
# Copy this file to .env and edit values as needed.
# Values shown here are the application defaults.

# -----------------------
# Weaviate Configuration
# -----------------------
WEAVIATE_HOST=localhost
WEAVIATE_PORT=8080

# -----------------------
# Importer Configuration
# -----------------------
IMPORTER_TICKETS_DIR=tickets
IMPORTER_BATCH_SIZE=300
IMPORTER_MAX_WORKERS=20
IMPORTER_MAX_FILE_SIZE_BYTES=1000000

# -----------------------
# Agent Configuration
# -----------------------
AGENT_CONTEXT_TOKEN_THRESHOLD=29000
AGENT_LARGE_MESSAGE_RATIO=0.90
AGENT_PLANNING_ENABLED=true
AGENT_MAX_ITERATIONS=200
AGENT_LOOP_DETECTION_ENABLED=true
AGENT_LOOP_ACTION_WINDOW_SIZE=20
AGENT_LOOP_REPETITION_THRESHOLD=8
AGENT_LOOP_ERROR_THRESHOLD=8
AGENT_LOOP_PATTERN_LENGTH=10
AGENT_COMPRESSION_ENABLED=true
AGENT_COMPRESSION_MIN_TOKENS=1000
AGENT_COMPRESSION_MIN_CHARS=5000
AGENT_UNSAFE_MODE=false

# -----------------------
# Chat Configuration
# -----------------------
CHAT_SAVE_HISTORY=true
CHAT_HISTORY_DIR=chat_history
CHAT_MAX_ITERATIONS=25

# -----------------------
# REST Server Configuration
# -----------------------
SERVER_HOST=localhost
SERVER_PORT=9720
SERVER_ENFORCE_SYSTEM_PROMPT=true
SERVER_API_KEY=

# -----------------------
# MCP Server Configuration
# -----------------------
MCP_ENABLED=true
MCP_TRANSPORT=stdio
MCP_SSE_HOST=localhost
MCP_SSE_PORT=9721
MCP_TIMEOUT_SECONDS=30
MCP_AUTH_REQUIRED=false
MCP_AUTH_TOKEN=

# -----------------------
# LLM Provider Configuration
# -----------------------
LLM_PROVIDER=auto

# OpenAI provider
OPENAI_API_KEY=
OPENAI_API_BASE=
OPENAI_MODEL=gpt-4o-mini

# vLLM provider
VLLM_API_URL=http://vllm:8000
VLLM_MODEL=meta-llama/Llama-2-13b-chat-hf

# Ollama provider
OLLAMA_API_URL=http://ollama:11434
OLLAMA_MODEL=glm-4.7-flash
EMBEDDING_MODEL=nomic-embed-text

# Common provider tuning
CHUNK_SIZE_BYTES=2000
"""

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration with environment variable overrides."""
        config = cls()
        config.weaviate.host = os.getenv("WEAVIATE_HOST", config.weaviate.host)
        config.weaviate.port = int(os.getenv("WEAVIATE_PORT", config.weaviate.port))
        config.importer.max_file_size_bytes = int(os.getenv(
            "IMPORTER_MAX_FILE_SIZE_BYTES", config.importer.max_file_size_bytes
        ))
        config.agent.context_token_threshold = int(os.getenv(
            "AGENT_CONTEXT_TOKEN_THRESHOLD",
            config.agent.context_token_threshold,
        ))
        config.agent.large_message_ratio = float(os.getenv(
            "AGENT_LARGE_MESSAGE_RATIO",
            config.agent.large_message_ratio,
        ))
        config.agent.planning_enabled = os.getenv(
            "AGENT_PLANNING_ENABLED", "true"
        ).lower() in ("true", "1", "yes")
        config.agent.max_iterations = int(os.getenv(
            "AGENT_MAX_ITERATIONS", config.agent.max_iterations
        ))
        config.agent.loop_detection_enabled = os.getenv(
            "AGENT_LOOP_DETECTION_ENABLED", "true"
        ).lower() in ("true", "1", "yes")
        config.agent.loop_action_window_size = int(os.getenv(
            "AGENT_LOOP_ACTION_WINDOW_SIZE", config.agent.loop_action_window_size
        ))
        config.agent.loop_repetition_threshold = int(os.getenv(
            "AGENT_LOOP_REPETITION_THRESHOLD", config.agent.loop_repetition_threshold
        ))
        config.agent.loop_error_threshold = int(os.getenv(
            "AGENT_LOOP_ERROR_THRESHOLD", config.agent.loop_error_threshold
        ))
        config.agent.loop_pattern_length = int(os.getenv(
            "AGENT_LOOP_PATTERN_LENGTH", config.agent.loop_pattern_length
        ))
        config.agent.compression_enabled = os.getenv(
            "AGENT_COMPRESSION_ENABLED", "true"
        ).lower() in ("true", "1", "yes")
        config.agent.compression_min_tokens = int(os.getenv(
            "AGENT_COMPRESSION_MIN_TOKENS", config.agent.compression_min_tokens
        ))
        config.agent.compression_min_chars = int(os.getenv(
            "AGENT_COMPRESSION_MIN_CHARS", config.agent.compression_min_chars
        ))
        config.agent.unsafe_mode = os.getenv(
            "AGENT_UNSAFE_MODE", "false"
        ).lower() in ("true", "1", "yes")
        config.chat.save_history = os.getenv(
            "CHAT_SAVE_HISTORY", "true"
        ).lower() in ("true", "1", "yes")
        config.chat.history_dir = os.getenv(
            "CHAT_HISTORY_DIR", config.chat.history_dir
        )
        config.chat.max_iterations = int(os.getenv(
            "CHAT_MAX_ITERATIONS", config.chat.max_iterations
        ))
        config.server.host = os.getenv("SERVER_HOST", config.server.host)
        config.server.port = int(os.getenv("SERVER_PORT", config.server.port))
        config.server.enforce_system_prompt = os.getenv(
            "SERVER_ENFORCE_SYSTEM_PROMPT", "true"
        ).lower() in ("true", "1", "yes")
        config.server.api_key = os.getenv("SERVER_API_KEY", "")

        # MCP configuration
        config.mcp.enabled = os.getenv(
            "MCP_ENABLED", "true"
        ).lower() in ("true", "1", "yes")
        config.mcp.transport = os.getenv("MCP_TRANSPORT", config.mcp.transport)
        config.mcp.sse_host = os.getenv("MCP_SSE_HOST", config.mcp.sse_host)
        config.mcp.sse_port = int(os.getenv("MCP_SSE_PORT", config.mcp.sse_port))
        config.mcp.timeout_seconds = int(os.getenv(
            "MCP_TIMEOUT_SECONDS", config.mcp.timeout_seconds
        ))
        config.mcp.auth_required = os.getenv(
            "MCP_AUTH_REQUIRED", "false"
        ).lower() in ("true", "1", "yes")
        config.mcp.auth_token = os.getenv("MCP_AUTH_TOKEN", config.mcp.auth_token)
        
        # LLM Provider configuration
        config.llm_provider.provider = os.getenv(
            "LLM_PROVIDER", config.llm_provider.provider
        )
        config.llm_provider.openai_api_key = os.getenv(
            "OPENAI_API_KEY", config.llm_provider.openai_api_key
        )
        config.llm_provider.openai_api_base = os.getenv(
            "OPENAI_API_BASE", config.llm_provider.openai_api_base
        )
        config.llm_provider.openai_model = os.getenv(
            "OPENAI_MODEL", config.llm_provider.openai_model
        )
        config.llm_provider.vllm_api_url = os.getenv(
            "VLLM_API_URL", config.llm_provider.vllm_api_url
        )
        config.llm_provider.vllm_model = os.getenv(
            "VLLM_MODEL", config.llm_provider.vllm_model
        )
        config.llm_provider.ollama_api_url = os.getenv(
            "OLLAMA_API_URL", config.llm_provider.ollama_api_url
        )
        config.llm_provider.ollama_model = os.getenv(
            "OLLAMA_MODEL", config.llm_provider.ollama_model
        )
        config.llm_provider.embedding_model = os.getenv(
            "EMBEDDING_MODEL", config.llm_provider.embedding_model
        )
        config.llm_provider.chunk_size_bytes = int(os.getenv(
            "CHUNK_SIZE_BYTES", config.llm_provider.chunk_size_bytes
        ))
        return config

    def get_weaviate_vector_config(self):
        """Get Weaviate vector config based on selected provider.
        
        Raises ValueError if provider is not explicitly configured.
        """
        from weaviate.classes.config import Configure
        
        provider = self.llm_provider.provider.lower()
        
        if provider == "openai":
            if not self.llm_provider.openai_api_key:
                raise ValueError("OpenAI provider selected but OPENAI_API_KEY is not set")
            return Configure.Vectors.text2vec_openai(
                api_key=self.llm_provider.openai_api_key,
                base_url=self.llm_provider.openai_api_base if self.llm_provider.openai_api_base else None,
            )
        
        elif provider == "ollama":
            return Configure.Vectors.text2vec_ollama(
                api_endpoint=self.llm_provider.ollama_api_url,
                model=self.llm_provider.embedding_model,
            )
        
        elif provider == "vllm":
            return Configure.Vectors.text2vec_ollama(
                api_endpoint=self.llm_provider.vllm_api_url,
                model=self.llm_provider.embedding_model,
            )
        
        elif provider == "auto":
            # Auto mode: OpenAI if API key is configured, otherwise error
            if self.llm_provider.openai_api_key:
                return Configure.Vectors.text2vec_openai(
                    api_key=self.llm_provider.openai_api_key,
                    base_url=self.llm_provider.openai_api_base if self.llm_provider.openai_api_base else None,
                )
            else:
                raise ValueError(
                    "Provider set to 'auto' but no OPENAI_API_KEY configured. "
                    "Set LLM_PROVIDER explicitly or provide OPENAI_API_KEY"
                )
        
        else:
            raise ValueError(f"Unknown provider: {provider}. Must be 'openai', 'ollama', 'vllm', or 'auto'")

    def get_weaviate_generative_config(self):
        """Get Weaviate generative model config based on selected provider.
        
        Raises ValueError if provider is not explicitly configured.
        """
        from weaviate.classes.config import GenerativeConfig
        
        provider = self.llm_provider.provider.lower()
        
        if provider == "openai":
            if not self.llm_provider.openai_api_key:
                raise ValueError("OpenAI provider selected but OPENAI_API_KEY is not set")
            return GenerativeConfig.openai(
                api_key=self.llm_provider.openai_api_key,
                base_url=self.llm_provider.openai_api_base if self.llm_provider.openai_api_base else None,
                model=self.llm_provider.openai_model,
            )
        
        elif provider == "ollama":
            return GenerativeConfig.ollama(
                api_endpoint=self.llm_provider.ollama_api_url,
                model=self.llm_provider.ollama_model,
            )
        
        elif provider == "vllm":
            return GenerativeConfig.ollama(
                api_endpoint=self.llm_provider.vllm_api_url,
                model=self.llm_provider.vllm_model,
            )
        
        elif provider == "auto":
            # Auto mode: OpenAI if API key is configured, otherwise error
            if self.llm_provider.openai_api_key:
                return GenerativeConfig.openai(
                    api_key=self.llm_provider.openai_api_key,
                    base_url=self.llm_provider.openai_api_base if self.llm_provider.openai_api_base else None,
                    model=self.llm_provider.openai_model,
                )
            else:
                raise ValueError(
                    "Provider set to 'auto' but no OPENAI_API_KEY configured. "
                    "Set LLM_PROVIDER explicitly or provide OPENAI_API_KEY"
                )
        
        else:
            raise ValueError(f"Unknown provider: {provider}. Must be 'openai', 'ollama', 'vllm', or 'auto'")
