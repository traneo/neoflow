# vLLM Setup Guide

This document explains how to configure and run NeoFlow with vLLM as the LLM provider.

## Overview

vLLM is a high-performance inference server optimized for LLM serving. It provides an OpenAI-compatible API and excellent throughput for local deployments.

## Prerequisites

- NVIDIA GPU with CUDA support
- Docker with NVIDIA container runtime
- Sufficient VRAM for your chosen model (minimum 8GB recommended)

## Docker Compose Configuration

To enable vLLM services, uncomment the relevant sections in your `docker-compose.yaml` file:

### Agent Model Service (vllm-agent)

```yaml
vllm-agent:
  image: vllm/vllm-openai:cu130-nightly-x86_64
  container_name: vllm-agent
  runtime: nvidia
  ports:
    - "8000:8000"
  volumes:
    - vllm_models:/root/.cache/huggingface
  environment:
    HF_TOKEN: your_huggingface_token_here  # Replace with your actual token
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            count: all
            capabilities: [gpu]
  command: >
    unsloth/GLM-4.7-Flash --trust-remote-code
  restart: unless-stopped
```

### Embedding Model Service (vllm-embed)

```yaml
vllm-embed:
  image: vllm/vllm-openai:cu130-nightly-x86_64
  container_name: vllm-embed
  runtime: nvidia
  ports:
    - "8001:8000"
  volumes:
    - vllm_models:/root/.cache/huggingface
  environment:
    HF_TOKEN: your_huggingface_token_here  # Replace with your actual token
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            count: all
            capabilities: [gpu]
  command: >
    nomic-ai/nomic-embed-text-v1.5 --trust-remote-code
  restart: unless-stopped
```

### Volume Configuration

Add the vllm_models volume to your volumes section:

```yaml
volumes:
  weaviate_data:
  ollama:
  vllm_models:
```

## Environment Configuration

Set the following environment variables to use vLLM:

```bash
# Set vLLM as the provider
export LLM_PROVIDER=vllm

# Configure vLLM endpoints
export VLLM_API_URL=http://localhost:8000
export VLLM_MODEL=unsloth/GLM-4.7-Flash

# For embeddings (if using vllm-embed service)
export EMBEDDING_MODEL=nomic-ai/nomic-embed-text-v1.5
```

## Starting the Services

1. **Get a HuggingFace token** (for downloading models):
   - Visit https://huggingface.co/settings/tokens
   - Create a token with read access
   - Replace `your_huggingface_token_here` in the docker-compose file

2. **Start the services**:
   ```bash
   docker compose up -d vllm-agent vllm-embed
   ```

3. **Wait for models to download**:
   First startup will download models (can take 10-30 minutes depending on your connection)
   ```bash
   docker compose logs -f vllm-agent
   ```

4. **Verify the service is ready**:
   ```bash
   curl http://localhost:8000/health
   ```

## Model Selection

You can use different models by changing the `command` parameter. Popular options:

### Recommended Models for Agent Work

- `unsloth/GLM-4.7-Flash` - Fast, good quality (default)
- `meta-llama/Llama-2-13b-chat-hf` - Balanced performance
- `mistralai/Mistral-7B-Instruct-v0.2` - Efficient instruction following

### Embedding Models

- `nomic-ai/nomic-embed-text-v1.5` - High quality (default)
- `BAAI/bge-large-en-v1.5` - Alternative high-quality option

## Performance Tuning

### Memory Optimization

If you encounter OOM (Out of Memory) errors:

```yaml
command: >
  unsloth/GLM-4.7-Flash 
  --trust-remote-code 
  --max-model-len 4096
  --gpu-memory-utilization 0.9
```

### Multiple GPUs

To use specific GPUs:

```yaml
environment:
  CUDA_VISIBLE_DEVICES: "0,1"  # Use GPUs 0 and 1
```

## Troubleshooting

### Issue: "CUDA out of memory"

**Solution**: Use a smaller model or reduce `max-model-len`:
```bash
--max-model-len 2048
```

### Issue: Models not downloading

**Solution**: Check HuggingFace token permissions and network connectivity:
```bash
docker compose logs vllm-agent
```

### Issue: Slow inference

**Solution**: 
1. Ensure you're using GPU (check `nvidia-smi`)
2. Increase `--gpu-memory-utilization` (default 0.9)
3. Use a smaller/faster model

## Switching Between Providers

NeoFlow supports automatic fallback between providers. To switch from Ollama to vLLM:

```bash
# Method 1: Environment variable
export LLM_PROVIDER=vllm

# Method 2: Command line flag
neoflow --provider vllm interactive

# Method 3: Auto-detect (tries OpenAI, vLLM, then Ollama)
export LLM_PROVIDER=auto
```

## Resource Requirements

| Model Size | Minimum VRAM | Recommended VRAM |
|------------|--------------|------------------|
| 7B         | 8GB          | 12GB            |
| 13B        | 16GB         | 24GB            |
| 34B        | 24GB         | 40GB            |

## Additional Resources

- [vLLM Documentation](https://docs.vllm.ai/)
- [HuggingFace Model Hub](https://huggingface.co/models)
- [vLLM Performance Tuning](https://docs.vllm.ai/en/latest/performance_tuning/)
