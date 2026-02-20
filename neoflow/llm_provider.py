"""
LLM Provider abstraction for multi-backend support.

Supports Ollama, vLLM, and OpenAI as LLM backends. Allows runtime selection
and automatic fallback based on available services and environment configuration.
"""

import os
import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

logger = logging.getLogger(__name__)


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    def create_chat_completion(
        self, messages: list[dict], model: Optional[str] = None, **kwargs
    ) -> dict[str, Any]:
        """
        Create a chat completion response.

        Args:
            messages: List of message dicts with 'role' and 'content' keys
            model: Model name/identifier for this provider
            **kwargs: Additional provider-specific parameters

        Returns:
            Response dict with at minimum 'choices' containing message content
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this provider is available/reachable."""
        pass

    @abstractmethod
    def get_name(self) -> str:
        """Get provider name."""
        pass


class OllamaProvider(LLMProvider):
    """Ollama local LLM provider."""

    def __init__(self, endpoint: Optional[str] = None):
        """
        Initialize Ollama provider.

        Args:
            endpoint: Ollama API endpoint (default: OLLAMA_API_URL, http://ollama:11434, or http://localhost:11434)
        """
        self.endpoint = endpoint or os.environ.get("OLLAMA_API_URL")
        if not self.endpoint:
            # Default to Docker hostname first, will fall back to localhost in is_available
            self.endpoint = "http://ollama:11434"
        self._fallback_endpoint = "http://localhost:11434"

    def get_name(self) -> str:
        return "ollama"

    def is_available(self) -> bool:
        """Check if Ollama service is reachable (tries Docker hostname and localhost)."""
        try:
            import requests

            # Try primary endpoint
            try:
                response = requests.get(f"{self.endpoint}/api/tags", timeout=2)
                if response.status_code == 200:
                    return True
            except Exception:
                pass
            
            # Try fallback endpoint (localhost)
            try:
                response = requests.get(f"{self._fallback_endpoint}/api/tags", timeout=2)
                if response.status_code == 200:
                    # Update endpoint to use localhost since Docker hostname didn't work
                    self.endpoint = self._fallback_endpoint
                    return True
            except Exception:
                pass
            
            return False
        except Exception as e:
            logger.debug(f"Ollama not available: {e}")
            return False

    def create_chat_completion(
        self, messages: list[dict], model: Optional[str] = None, **kwargs
    ) -> dict[str, Any]:
        """Create chat completion via Ollama HTTP API using requests."""
        try:
            import requests
            import json

            # Use provided model or fall back to environment/default
            if model is None:
                model = os.environ.get("OLLAMA_AGENT_MODEL", "qwen3-coder:latest")

            # Use requests with explicit session cleanup
            with requests.Session() as session:
                response = session.post(
                    f"{self.endpoint}/api/chat",
                    json={
                        "model": model,
                        "messages": messages,
                        "stream": False,  # Disable streaming for simpler response handling
                        **kwargs,
                    },
                    timeout=300,
                )
                response.raise_for_status()
                data = response.json()
                
                # Normalize response to match OpenAI format
                usage = {
                    "prompt_tokens": data.get("prompt_eval_count", 0),
                    "completion_tokens": data.get("eval_count", 0),
                }
                usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]
                return {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": data.get("message", {}).get("content", ""),
                            }
                        }
                    ],
                    "model": model,
                    "usage": usage,
                }
        except requests.exceptions.Timeout as e:
            logger.error(f"Ollama chat completion timeout: {e}")
            raise TimeoutError(f"Ollama request timed out after 300 seconds") from e
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Ollama connection error: {e}")
            raise ConnectionError(f"Cannot connect to Ollama at {self.endpoint}") from e
        except Exception as e:
            logger.error(f"Ollama chat completion failed: {e}")
            raise


class VLLMProvider(LLMProvider):
    """vLLM local LLM provider (OpenAI-compatible API)."""

    def __init__(self, api_url: Optional[str] = None):
        """
        Initialize vLLM provider.

        Args:
            api_url: vLLM API endpoint (default: VLLM_API_URL or http://vllm:8000)
        """
        self.api_url = api_url or os.environ.get("VLLM_API_URL", "http://vllm:8000")

    def get_name(self) -> str:
        return "vllm"

    def is_available(self) -> bool:
        """Check if vLLM service is reachable."""
        try:
            import requests

            response = requests.get(f"{self.api_url}/health", timeout=2)
            return response.status_code == 200
        except Exception as e:
            logger.debug(f"vLLM not available: {e}")
            return False

    def create_chat_completion(
        self, messages: list[dict], model: Optional[str] = None, **kwargs
    ) -> dict[str, Any]:
        """Create chat completion via vLLM OpenAI-compatible API."""
        try:
            import requests

            if model is None:
                model = os.environ.get("VLLM_MODEL", "meta-llama/Llama-2-7b")

            response = requests.post(
                f"{self.api_url}/v1/chat/completions",
                json={
                    "model": model,
                    "messages": messages,
                    **kwargs,
                },
                timeout=300,
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.Timeout as e:
            logger.error(f"vLLM chat completion timeout: {e}")
            raise TimeoutError(f"vLLM request timed out after 300 seconds") from e
        except requests.exceptions.ConnectionError as e:
            logger.error(f"vLLM connection error: {e}")
            raise ConnectionError(f"Cannot connect to vLLM at {self.api_url}") from e
        except Exception as e:
            logger.error(f"vLLM chat completion failed: {e}")
            raise


class OpenAIProvider(LLMProvider):
    """OpenAI cloud LLM provider."""

    def __init__(self, api_key: Optional[str] = None, api_base: Optional[str] = None):
        """
        Initialize OpenAI provider.

        Args:
            api_key: OpenAI API key (default: OPENAI_API_KEY env var)
            api_base: OpenAI API base URL (default: OPENAI_API_BASE env var, or OpenAI default)
        """
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.api_base = api_base or os.environ.get("OPENAI_API_BASE")

        if not self.api_key:
            logger.warning("OPENAI_API_KEY not set; OpenAI provider will fail")

    def get_name(self) -> str:
        return "openai"

    def is_available(self) -> bool:
        """Check if OpenAI API key is configured."""
        return bool(self.api_key)

    def create_chat_completion(
        self, messages: list[dict], model: Optional[str] = None, **kwargs
    ) -> dict[str, Any]:
        """Create chat completion via OpenAI SDK."""
        try:
            import openai

            if not self.api_key:
                raise ValueError("OPENAI_API_KEY not configured")

            # Configure client
            if self.api_base:
                client = openai.OpenAI(api_key=self.api_key, base_url=self.api_base)
            else:
                client = openai.OpenAI(api_key=self.api_key)

            if model is None:
                model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

            response = client.chat.completions.create(
                model=model,
                messages=messages,
                timeout=300.0,
                **kwargs,
            )

            # Normalize response to match standard format
            return {
                "choices": [
                    {
                        "message": {
                            "role": response.choices[0].message.role,
                            "content": response.choices[0].message.content,
                        }
                    }
                ],
                "model": model,
                "usage": {
                    "prompt_tokens": getattr(response.usage, "prompt_tokens", 0) if getattr(response, "usage", None) else 0,
                    "completion_tokens": getattr(response.usage, "completion_tokens", 0) if getattr(response, "usage", None) else 0,
                    "total_tokens": getattr(response.usage, "total_tokens", 0) if getattr(response, "usage", None) else 0,
                },
            }
        except openai.APITimeoutError as e:
            logger.error(f"OpenAI chat completion timeout: {e}")
            raise TimeoutError(f"OpenAI request timed out after 300 seconds") from e
        except openai.APIConnectionError as e:
            logger.error(f"OpenAI connection error: {e}")
            raise ConnectionError(f"Cannot connect to OpenAI API") from e
        except Exception as e:
            logger.error(f"OpenAI chat completion failed: {e}")
            raise


def get_provider(provider_name: Optional[str] = None) -> LLMProvider:
    """
    Get an LLM provider instance.

    Selection logic:
    1. If provider_name is explicitly given, use that
    2. If LLM_PROVIDER env var is set, use that
    3. Auto-detect: OpenAI (if API key present) -> vLLM -> Ollama

    Args:
        provider_name: Optional explicit provider name: 'openai', 'vllm', 'ollama'

    Returns:
        An LLMProvider instance

    Raises:
        ValueError: If selected provider is not available
    """
    explicit = provider_name or os.environ.get("LLM_PROVIDER")

    # Explicit provider selection (but not "auto")
    if explicit and explicit.lower() != "auto":
        explicit_lower = explicit.lower()
        
        if explicit_lower == "openai":
            provider = OpenAIProvider()
        elif explicit_lower == "vllm":
            provider = VLLMProvider()
        elif explicit_lower == "ollama":
            provider = OllamaProvider()
        else:
            raise ValueError(
                f"Unknown LLM provider: {explicit}. Choose from: openai, vllm, ollama, auto"
            )

        if not provider.is_available():
            # If the user explicitly requested a provider, prefer returning
            # the configured instance and let downstream calls surface
            # connectivity/errors. This allows running in environments
            # where availability checks may be unreliable (e.g. local
            # sockets, proxies, or startup race conditions).
            logger.warning(
                "Specified provider '%s' is not available (is_available() returned False); returning provider instance and proceeding",
                explicit,
            )
            return provider
        logger.info(f"Using LLM provider: {provider.get_name()}")
        return provider

    # Auto-detect (either explicit=None or explicit="auto")
    logger.info("Auto-detecting LLM provider...")

    # Prefer OpenAI if API key is present
    if os.environ.get("OPENAI_API_KEY"):
        logger.info("Using LLM provider: openai (API key detected)")
        return OpenAIProvider()

    # Try vLLM
    vllm_provider = VLLMProvider()
    if vllm_provider.is_available():
        logger.info("Using LLM provider: vllm")
        return vllm_provider

    # Fall back to Ollama
    ollama_provider = OllamaProvider()
    if ollama_provider.is_available():
        logger.info("Using LLM provider: ollama")
        return ollama_provider

    # No provider available
    raise RuntimeError(
        "No LLM provider available. Configure OPENAI_API_KEY, check vLLM service, "
        "or ensure Ollama is running."
    )
