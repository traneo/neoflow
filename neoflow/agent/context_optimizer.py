"""Context optimization middleware for the agent loop.

Prevents unbounded context growth by deduplicating assistant messages,
pruning stale file listings, and summarizing old context when the token
count approaches a configurable threshold.

Dictionary Substitution Compression:
When run_command actions produce large outputs, dictionary compression is
applied to reduce token count before summarization. The compressed text is
stored in message history, but automatically decompressed before sending to
the LLM, ensuring the agent sees and responds with normal text.
"""

import logging

from neoflow.llm_provider import get_provider

from neoflow.config import Config
from neoflow.status_bar import StatusBar, estimate_tokens
from neoflow.agent.dictionary_compression import (
    compress_text,
    decompress_text,
    should_compress,
)

logger = logging.getLogger(__name__)

_SUMMARIZATION_PROMPT = (
    "Summarize the following agent conversation context concisely, "
    "preserving all key decisions, file paths, action results, and "
    "current task state:\n\n"
)


class ContextOptimizer:
    """Middleware that optimizes the message list between agent steps."""

    def __init__(
        self,
        config: Config,
        status_bar: StatusBar,
        provider=None,
        token_threshold: int | None = None,
        large_message_ratio: float | None = None,
    ) -> None:
        self._config = config
        self._status_bar = status_bar
        self._provider = provider
        self._token_threshold = (
            token_threshold
            if token_threshold is not None
            else config.agent.context_token_threshold
        )
        self._large_message_ratio = (
            large_message_ratio
            if large_message_ratio is not None
            else config.agent.large_message_ratio
        )

    # -- Public API ----------------------------------------------------------

    def add_message(
        self,
        messages: list[dict],
        message: dict,
        source_action: str | None = None,
    ) -> list[dict]:
        """Add a message, applying compression if needed, then summarizing if still too large.

        Dictionary compression is applied to run_command outputs before the
        large-message check, potentially avoiding summarization entirely.

        *source_action* is internal metadata that can be used for tracking.
        """
        if source_action:
            message["_source_action"] = source_action

        content = message.get("content", "")
        
        # Apply dictionary compression for run_command outputs if enabled
        if (
            self._config.agent.compression_enabled
            and source_action == "run_command"
            and should_compress(
                content,
                min_size_chars=self._config.agent.compression_min_chars,
                min_size_tokens=self._config.agent.compression_min_tokens,
            )
        ):
            self._status_bar.set_loading(True, "Compressing Message...")
            logger.info("Applying dictionary compression to run_command output")
            compression_result = compress_text(content)
            self._status_bar.set_loading(False)
            
            if compression_result.compression_ratio < 0.95:  # At least 5% savings
                logger.info(
                    f"Compression saved {(1 - compression_result.compression_ratio) * 100:.1f}%: "
                    f"{compression_result.original_size} -> {compression_result.compressed_size} chars"
                )
                # Store compressed content and dictionary as metadata
                message = dict(message)  # shallow copy
                message["content"] = compression_result.compressed_text
                message["_compression_dict"] = compression_result.dictionary
                content = compression_result.compressed_text
        
        # Pass 4: large-message pre-check (uses compressed content if available)
        token_est = estimate_tokens(content)
        large_limit = int(self._token_threshold * self._large_message_ratio)

        if token_est > large_limit:
            self._status_bar.set_loading(True, "Optimizing Context Window...")
            try:
                summary = self._summarize_text(content)
                message = dict(message)  # shallow copy
                message["content"] = f"[Summarized Result]\n{summary}"
            finally:
                self._status_bar.set_loading(False)

        messages.append(message)
        return messages

    def optimize(self, messages: list[dict]) -> list[dict]:
        """Run all optimization passes in-place and return the list."""
        self._pass_dedup_assistant(messages)
        self._pass_token_summarization(messages)
        self._update_token_count(messages)
        return messages

    # -- Pass 1: assistant message deduplication -----------------------------

    @staticmethod
    def _pass_dedup_assistant(messages: list[dict]) -> None:
        """Keep only the last 10 assistant messages, remove older ones."""
        indices = [
            i for i, m in enumerate(messages) if m.get("role") == "assistant"
        ]
        if len(indices) <= 10:
            return
        to_remove = set(indices[:-10])
        for idx in sorted(to_remove, reverse=True):
            del messages[idx]

    # -- Pass 2: token-threshold summarization ------------------------------

    def _pass_token_summarization(self, messages: list[dict]) -> None:
        """If total tokens exceed the threshold, summarize middle messages."""
        total = sum(estimate_tokens(m.get("content", "")) for m in messages)
        if total <= self._token_threshold:
            return

        self._status_bar.set_loading(True, "Optimizing Context Window...")
        try:
            # Keep first 4 messages (system + initial context) and last 4
            keep_head = min(4, len(messages))
            keep_tail = min(4, len(messages) - keep_head)
            if keep_tail <= 0:
                return  # Not enough messages to summarize

            middle = messages[keep_head : len(messages) - keep_tail]
            if not middle:
                return

            # Strip internal metadata before building the summary text
            text_parts: list[str] = []
            for m in middle:
                role = m.get("role", "unknown")
                content = m.get("content", "")
                text_parts.append(f"[{role}]: {content}")
            combined = "\n\n".join(text_parts)

            summary = self._summarize_text(combined)

            # Replace middle section with a single summary message
            summary_msg: dict = {
                "role": "user",
                "content": f"[Context Summary]\n{summary}",
            }
            messages[keep_head : len(messages) - keep_tail] = [summary_msg]
        finally:
            self._status_bar.set_loading(False)

    # -- Helpers -------------------------------------------------------------

    def _summarize_text(self, text: str) -> str:
        """Call the LLM to produce a concise summary."""
        try:
            provider = self._provider or get_provider(self._config.llm_provider.provider)
            model = getattr(self._config.llm_provider, f"{provider.get_name()}_model", None)
            response = provider.create_chat_completion(
                messages=[{"role": "user", "content": _SUMMARIZATION_PROMPT + text}],
                model=model,
            )
            # Extract content
            if isinstance(response, dict):
                if "choices" in response and response["choices"]:
                    choice = response["choices"][0]
                    if isinstance(choice, dict) and "message" in choice:
                        return choice["message"].get("content", "")
                    return choice.get("text", "")
                return response.get("message", {}).get("content", "")
        except Exception:
            logger.warning("Summarization failed, truncating instead", exc_info=True)
            # Fallback: keep the first ~2000 chars as a rough summary
            return text[:2000] + "\n... (truncated)"

    def _update_token_count(self, messages: list[dict]) -> None:
        """Recalculate and push the token count to the status bar."""
        total = sum(estimate_tokens(m.get("content", "")) for m in messages)
        with self._status_bar._lock:
            self._status_bar._state.token_count = total

    def strip_metadata(self, messages: list[dict]) -> list[dict]:
        """Return a copy of messages with internal metadata removed and compressed content decompressed.

        Call this before sending messages to the LLM so that:
        1. Internal metadata fields like ``_source_action`` are not leaked
        2. Dictionary-compressed messages are decompressed to normal text
        
        This ensures the agent sees and responds with normal text, unaware of compression.
        """
        cleaned: list[dict] = []
        has_compressed = any("_compression_dict" in m for m in messages)
        
        if has_compressed:
            self._status_bar.set_loading(True, "Decompressing Messages...")
        
        for m in messages:
            # Check if message has compression dictionary
            if "_compression_dict" in m:
                # Decompress the content before removing metadata
                compression_dict = m.get("_compression_dict", {})
                content = m.get("content", "")
                decompressed_content = decompress_text(content, compression_dict)
                
                # Create cleaned message with decompressed content
                m2 = {k: v for k, v in m.items() if not k.startswith("_")}
                m2["content"] = decompressed_content
                cleaned.append(m2)
            elif "_source_action" in m or any(k.startswith("_") for k in m.keys()):
                # Has metadata but no compression - just strip metadata
                m2 = {k: v for k, v in m.items() if not k.startswith("_")}
                cleaned.append(m2)
            else:
                # No metadata, use as-is
                cleaned.append(m)
        
        if has_compressed:
            self._status_bar.set_loading(False)
        
        return cleaned
