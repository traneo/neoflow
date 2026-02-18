# LLM Providers

Complete guide to LLM provider configuration and usage in NeoFlow.

## Table of Contents

- [Overview](#overview)
- [Supported Providers](#supported-providers)
- [Configuration](#configuration)
- [Provider Selection](#provider-selection)
- [Usage Examples](#usage-examples)
- [Troubleshooting](#troubleshooting)

## Overview

NeoFlow supports multiple LLM backends, allowing you to choose the best provider for your deployment scenario. The system provides automatic detection, fallback mechanisms, and unified configuration.

### Key Features

- **Multi-Provider**: Ollama, vLLM, and OpenAI support
- **Auto-Detection**: Automatically selects available provider
- **Fallback**: Falls back to alternate provider on failure
- **Unified Config**: Single configuration for LLM and embeddings
- **Easy Switching**: Change providers without code changes

## Supported Providers

### 1. Ollama (Default)

**Best For:**
- Local development
- Privacy-sensitive deployments
- Offline environments
- Cost control

**Pros:**
- Free and open-source
- Runs entirely local
- No API rate limits
- Supports many models

**Cons:**
- Requires local GPU (recommended)
- Slower than cloud options
- Limited to available hardware

**Setup:**
```bash
# Via Docker (included in docker-compose.yaml)
docker compose up -d ollama

# Or install locally
curl https://ollama.ai/install.sh | sh

# Pull a model
ollama pull qwen3-coder:latest
```

### 2. vLLM

**Best For:**
- Production deployments
- High throughput needs
- GPU clusters
- Performance-critical applications

**Pros:**
- Very fast inference
- Optimized for GPU
- Batch processing
- High concurrency

**Cons:**
- Requires GPU
- More complex setup
- Higher resource usage

**Setup:**
See [VLLM_SETUP.md](VLLM_SETUP.md) for detailed instructions.

### 3. OpenAI

**Best For:**
- Quick setup
- Best model quality
- No infrastructure management
- Experimentation

**Pros:**
- State-of-the-art models
- No infrastructure needed
- Reliable and fast
- Easy setup

**Cons:**
- Costs per request
- Requires internet
- Privacy considerations
- Rate limits

**Setup:**
```bash
export OPENAI_API_KEY=sk-your_key_here
```

## Configuration

### Unified Provider Config

In [config.py](../neoflow/config.py):

```python
@dataclass
class LLMProviderConfig:
    provider: str = "auto"  # 'auto', 'openai', 'vllm', 'ollama'
    
    # OpenAI
    openai_api_key: str = ""
    openai_api_base: str = ""
    openai_model: str = "gpt-4o-mini"
    
    # vLLM
    vllm_api_url: str = "http://vllm:8000"
    vllm_model: str = "meta-llama/Llama-2-13b-chat-hf"
    
    # Ollama
    ollama_api_url: str = "http://ollama:11434"
    ollama_model: str = "qwen3-coder:latest"
    
    # Embeddings (uses same provider)
    embedding_model: str = "nomic-embed-text"
    chunk_size_bytes: int = 2_000
```

### Environment Variables

```bash
# Provider Selection
export LLM_PROVIDER=ollama  # or vllm, openai, auto

# OpenAI Configuration
export OPENAI_API_KEY=sk-...
export OPENAI_API_BASE=https://api.openai.com/v1
export OPENAI_MODEL=gpt-4o-mini

# vLLM Configuration
export VLLM_API_URL=http://vllm:8000
export VLLM_MODEL=meta-llama/Llama-2-13b-chat-hf

# Ollama Configuration
export OLLAMA_API_URL=http://ollama:11434
export OLLAMA_MODEL=qwen3-coder:latest

# Embeddings
export EMBEDDING_MODEL=nomic-embed-text
```

## Provider Selection

### Auto-Detection (Default)

With `provider: "auto"`, NeoFlow tries providers in order:

1. **OpenAI**: If `OPENAI_API_KEY` is set
2. **vLLM**: If vLLM endpoint is reachable
3. **Ollama**: If Ollama endpoint is reachable

```python
# In code
from neoflow.llm_provider import get_provider

provider = get_provider()  # Auto-detects
print(f"Using: {provider.get_name()}")
```

### Explicit Selection

Force a specific provider:

```bash
export LLM_PROVIDER=ollama
```

Or in code:

```python
from neoflow.llm_provider import get_provider

provider = get_provider("ollama")
```

### Fallback Mechanism

If primary provider fails, system attempts fallback:

```
1. Try configured provider
   ↓ (fails)
2. Try auto-detection
   ↓
3. Use first available provider
```

## Model Selection

### Ollama Models

**Recommendations:**

**For Code:**
- `qwen3-coder:latest` - Fast, good code understanding
- `codellama:latest` - Specialized for code
- `deepseek-coder:latest` - Excellent for complex code

**For General:**
- `llama3:latest` - Balanced performance
- `mistral:latest` - Fast and efficient
- `mixtral:latest` - High quality

**Pull Models:**
```bash
ollama pull qwen3-coder:latest
ollama list  # See installed models
```

### vLLM Models

Any Hugging Face model compatible with vLLM:

- `meta-llama/Llama-2-13b-chat-hf`
- `codellama/CodeLlama-13b-hf`
- `deepseek-ai/deepseek-coder-6.7b-instruct`
- `mistralai/Mistral-7B-Instruct-v0.2`

### OpenAI Models

- `gpt-4o` - Most capable (expensive)
- `gpt-4o-mini` - Good balance (recommended)
- `gpt-3.5-turbo` - Fast and cheap

## Usage Examples

### Example 1: Ollama Setup

```bash
# 1. Start Ollama
docker compose up -d ollama

# 2. Pull model
docker exec -it neoflow-ollama ollama pull qwen3-coder:latest

# 3. Configure
export LLM_PROVIDER=ollama
export OLLAMA_MODEL=qwen3-coder:latest

# 4. Use
neoflow search -q "How to implement auth?"
```

### Example 2: OpenAI Setup

```bash
# 1. Get API key from platform.openai.com

# 2. Configure
export LLM_PROVIDER=openai
export OPENAI_API_KEY=sk-...
export OPENAI_MODEL=gpt-4o-mini

# 3. Use
neoflow agent "Create a login endpoint"
```

### Example 3: vLLM Setup

```bash
# 1. Start vLLM server (see VLLM_SETUP.md)

# 2. Configure
export LLM_PROVIDER=vllm
export VLLM_API_URL=http://vllm:8000
export VLLM_MODEL=meta-llama/Llama-2-13b-chat-hf

# 3. Use
neoflow serve
```

### Example 4: Switching Providers

```bash
# Start with Ollama
export LLM_PROVIDER=ollama
neoflow

# Switch to OpenAI
export LLM_PROVIDER=openai
export OPENAI_API_KEY=sk-...
neoflow

# Or use auto-detection
export LLM_PROVIDER=auto
neoflow
```

### Example 5: Provider in Code

```python
from neoflow.config import Config
from neoflow.llm_provider import get_provider

# Load config
config = Config.from_env()

# Get provider
provider = get_provider(config.llm_provider.provider)

# Use provider
response = provider.create_chat_completion(
    messages=[
        {"role": "user", "content": "Hello!"}
    ],
    model=config.llm_provider.ollama_model
)

print(response["choices"][0]["message"]["content"])
```

## Embeddings

### Embedding Models

For vector search, NeoFlow generates embeddings:

**Ollama:**
- `nomic-embed-text` - Recommended, good quality
- `mxbai-embed-large` - Larger, more accurate
- `all-minilm` - Fast, smaller

**OpenAI:**
- `text-embedding-3-small` - Good balance
- `text-embedding-3-large` - Most accurate
- `text-embedding-ada-002` - Legacy

**vLLM:**
- Can serve embedding models separately

### Configuration

```bash
# Ollama embeddings (default)
export EMBEDDING_MODEL=nomic-embed-text

# Ensure model is available
ollama pull nomic-embed-text
```

### Weaviate Integration

Embeddings are generated by Ollama/vLLM/OpenAI and stored in Weaviate:

```python
# Automatic in indexing
config.get_weaviate_vector_config()
# Returns proper vectorizer configuration
```

## Performance Tuning

### Ollama

**GPU Acceleration:**
```bash
# Check GPU availability
nvidia-smi

# Ollama automatically uses GPU if available
```

**Concurrent Requests:**
```bash
# Ollama handles concurrency automatically
# Adjust based on GPU memory
```

### vLLM

**Batch Size:**
```bash
# Start vLLM with custom batch size
vllm serve model_name --max-num-seqs 32
```

**Tensor Parallelism:**
```bash
# Use multiple GPUs
vllm serve model_name --tensor-parallel-size 2
```

### OpenAI

**Rate Limits:**
- Tier-based limits
- Use exponential backoff on errors
- Consider caching responses

## Troubleshooting

### Provider Not Available

**Check:**
```bash
# Ollama
curl http://localhost:11434/api/tags

# vLLM
curl http://localhost:8000/v1/models

# OpenAI
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY"
```

### Model Not Found

**Ollama:**
```bash
# List models
ollama list

# Pull missing model
ollama pull qwen3-coder:latest
```

**vLLM:**
- Check model name matches Hugging Face
- Ensure model is downloaded

**OpenAI:**
- Verify model name spelling
- Check API access level

### Slow Responses

**Ollama:**
- Check GPU usage: `nvidia-smi`
- Try smaller model
- Reduce context length

**vLLM:**
- Increase batch size
- Use tensor parallelism
- Check GPU memory

**OpenAI:**
- Already optimized
- Check network latency

### Out of Memory

**Symptoms:**
- Ollama crashes
- vLLM fails to start
- Responses halt mid-generation

**Solutions:**
1. Use smaller model:
   - Ollama: Try 7B instead of 13B
   - vLLM: Reduce model size
2. Reduce batch size
3. Lower context length
4. Add more GPU memory

### API Key Issues

**OpenAI:**
```bash
# Verify key is set
echo $OPENAI_API_KEY

# Test key
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY"
```

**Error "Invalid API key":**
- Regenerate key
- Check for leading/trailing spaces
- Verify key hasn't expired

## Best Practices

### 1. Development vs Production

**Development:**
- Use Ollama for free local testing
- Small models for speed
- Auto-detection for flexibility

**Production:**
- vLLM for performance
- OpenAI for simplicity
- Explicit provider selection

### 2. Cost Management

**Ollama:**
- Free but requires hardware
- One-time GPU investment

**vLLM:**
- GPU costs (cloud or on-prem)
- Optimized for throughput

**OpenAI:**
- Pay per request
- Monitor usage via dashboard
- Use cheaper models where appropriate

### 3. Model Selection

**Choose based on:**
- Task complexity (simple → small model)
- Latency requirements (fast → smaller)
- Quality needs (high → larger model)
- Budget constraints

### 4. Fallback Strategy

Always configure fallback:

```python
# Example config for reliability
LLM_PROVIDER=auto
OPENAI_API_KEY=sk-...  # Fallback to OpenAI
```

### 5. Monitoring

Track:
- Response times
- Error rates
- Token usage (OpenAI)
- GPU utilization (local)

## See Also

- [Configuration](CONFIGURATION.md)
- [VLLM Setup](VLLM_SETUP.md)
- [Performance](PERFORMANCE.md)
- [Deployment](DEPLOYMENT.md)
