"""Model prompt-format profiles.

Each :class:`ModelProfile` describes how system prompts (and optionally
messages) should be formatted for a specific model family.  The
:func:`resolve_model_profile` function selects the best profile for a given
model name using an ordered registry.

Adding a new model family
-------------------------
1. Subclass :class:`ModelProfile` and implement ``name``, ``matches``, and
   (optionally) ``wrap_system_prompt`` / ``format_messages``.
2. Instantiate it and insert it **before** :class:`DefaultProfile` in
   :data:`_PROFILE_REGISTRY`, or call :func:`register_profile` at runtime.

That's all — the agent picks up the new profile automatically.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------

class ModelProfile(ABC):
    """Defines prompt-formatting conventions for a model family.

    All methods have sensible no-op defaults so concrete profiles only need to
    override what actually differs from the standard OpenAI chat format.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier used in logs and diagnostics (e.g. ``"llama-instruct"``)."""
        ...

    @abstractmethod
    def matches(self, model_name: str) -> bool:
        """Return ``True`` if this profile should be applied for *model_name*.

        Matching is done case-insensitively.  More-specific profiles are placed
        earlier in :data:`_PROFILE_REGISTRY` so they win over broader ones.
        """
        ...

    def wrap_system_prompt(self, content: str) -> str:
        """Wrap *content* with model-specific system-prompt tags.

        The default implementation returns *content* unchanged, which is
        correct for any model that properly handles the ``"system"`` role in
        the OpenAI chat message format.
        """
        return content

    def format_messages(self, messages: list[dict]) -> list[dict]:
        """Transform the full messages list before it is sent to the LLM.

        Override this for models that require custom message merging or tag
        injection at the message level.  The default is a no-op.
        """
        return messages

    def clean_reply(self, text: str) -> str:
        """Post-process the raw LLM reply before parsing and display.

        Override this to strip model-specific control tokens or channel
        markers that would otherwise pollute ``parse_action`` or the agent
        display panel.  The default is a no-op.
        """
        return text

    def __repr__(self) -> str:
        return f"<ModelProfile name={self.name!r}>"


# ---------------------------------------------------------------------------
# Concrete profiles
# ---------------------------------------------------------------------------

class DefaultProfile(ModelProfile):
    """Fallback profile for OpenAI, Claude, and any OpenAI-API-compatible model.

    No special wrapping is applied — the API handles chat-template formatting
    server-side via the standard ``system`` / ``user`` / ``assistant`` roles.
    """

    @property
    def name(self) -> str:
        return "default"

    def matches(self, model_name: str) -> bool:
        # Used only as fallback; the registry logic never calls matches() on it
        # directly, but it must still implement the abstract method.
        return True


class LlamaInstructProfile(ModelProfile):
    """Llama 2 / Llama 3 instruct models.

    Llama instruct variants that run through a server *without* a built-in
    chat template (e.g. raw vLLM without ``--chat-template``) expect the
    system content wrapped in ``<<SYS>>`` / ``<</SYS>>`` delimiters inside
    the ``[INST]`` block.  Servers that *do* apply a chat template (Ollama,
    vLLM with ``--chat-template``) silently ignore the extra tags, so it is
    safe to always add them.
    """

    _PATTERNS: list[str] = [
        r"llama[-_.]?2",
        r"llama[-_.]?3",
        r"meta[-_.]?llama",
        r"llama[-_.]instruct",
        r"llama[-_.]chat",
    ]

    @property
    def name(self) -> str:
        return "llama-instruct"

    def matches(self, model_name: str) -> bool:
        lower = model_name.lower()
        return any(re.search(p, lower) for p in self._PATTERNS)

    def wrap_system_prompt(self, content: str) -> str:
        return f"<<SYS>>\n{content}\n<</SYS>>"


class QwenInstructProfile(ModelProfile):
    """Qwen / Qwen2 / Qwen3 instruct models.

    Qwen uses ``<|im_start|>`` / ``<|im_end|>`` chatml tags, but these are
    applied by the serving layer (Ollama, vLLM) via the chat template.  The
    system prompt content is passed as-is through the ``system`` role; no
    extra wrapping is needed.  This profile exists so that future Qwen-specific
    tweaks (e.g. thinking-budget tokens) have a natural home.
    """

    _PATTERNS: list[str] = [
        r"qwen",
    ]

    @property
    def name(self) -> str:
        return "qwen-instruct"

    def matches(self, model_name: str) -> bool:
        lower = model_name.lower()
        return any(re.search(p, lower) for p in self._PATTERNS)


class MistralInstructProfile(ModelProfile):
    """Mistral / Mixtral instruct models.

    Mistral models use ``[INST]`` / ``[/INST]`` delimiters, but the Mistral
    serving stack applies these automatically when the chat completions endpoint
    is used.  This profile is a placeholder for future Mistral-specific prompt
    adjustments.
    """

    _PATTERNS: list[str] = [
        r"mistral",
        r"mixtral",
    ]

    @property
    def name(self) -> str:
        return "mistral-instruct"

    def matches(self, model_name: str) -> bool:
        lower = model_name.lower()
        return any(re.search(p, lower) for p in self._PATTERNS)


class GPTOSSProfile(ModelProfile):
    """OpenAI gpt-oss-20b / gpt-oss-120b (Harmony response format).

    gpt-oss models are **exclusively** trained on the Harmony format and will
    not behave correctly without it.  Even when served through Ollama — which
    applies a Harmony-mimicking chat template automatically — the model still
    emits Harmony channel tokens inside its raw response text::

        <|start|>assistant<|channel|>analysis<|message|>
        I need to search for the file.
        <|start|>assistant<|channel|>final<|message|>
        Based on the task I will search for config.

        ```json
        {"action": "search_code", "query": "configuration"}
        ```
        <|end|>

    Harmony output channels
    -----------------------
    - ``analysis``   — internal chain-of-thought (should never reach the user)
    - ``commentary`` — tool call preambles / Harmony function calls
    - ``final``      — the user-facing / action-carrying output

    Harmony tool calling vs Neoflow tool calling
    --------------------------------------------
    Harmony's native tool-calling mechanism uses a TypeScript-like function
    namespace defined in the *developer* message and dispatches calls via the
    ``<|call|>`` stop token (commentary channel)::

        <|start|>assistant<|channel|>commentary to=functions.search
        <|constrain|>json<|message|>{"query": "foo"}<|call|>

    Neoflow does **not** use this mechanism.  Tools are described as plain
    text in the system prompt and the model is expected to emit exactly one
    ``{"action": "…", …}`` JSON block per turn.  The ``wrap_system_prompt``
    override reinforces this contract and explicitly tells the model to avoid
    Harmony tool calling.

    The ``clean_reply`` override strips all Harmony channel headers and stray
    special tokens from the raw LLM output so that ``parse_action`` and the
    agent display panel work correctly.
    """

    _PATTERNS: list[str] = [
        r"gpt[-_.]?oss",
    ]

    # Matches a full channel-header sequence:
    #   <|start|>{role}[optional modifiers]<|channel|>{channel}<|message|>
    # Uses non-greedy match so consecutive headers are each stripped separately.
    _CHANNEL_HEADER_RE = re.compile(
        r"<\|start\|>.*?<\|message\|>",
        re.DOTALL,
    )

    # Isolated Harmony special tokens that may survive after header stripping.
    _BARE_TOKEN_RE = re.compile(
        r"<\|(?:end|call|return|constrain)\|>",
    )

    @property
    def name(self) -> str:
        return "gpt-oss-harmony"

    def matches(self, model_name: str) -> bool:
        lower = model_name.lower()
        return any(re.search(p, lower) for p in self._PATTERNS)

    def wrap_system_prompt(self, content: str) -> str:
        """Append Harmony-specific output-format instructions to the system prompt.

        This reinforces Neoflow's JSON action format and prevents the model
        from using Harmony's native ``<|call|>`` tool-calling mechanism, which
        is incompatible with Neoflow's text-based tool dispatch.
        """
        harmony_note = (
            "\n\n# Harmony Output Instructions\n\n"
            "Place your step-by-step reasoning in the **analysis** channel and "
            "your JSON action in the **final** channel.\n\n"
            "IMPORTANT: Do NOT use Harmony tool calling (`<|call|>` / "
            "`functions` namespace). Instead, output exactly ONE ```json``` "
            "fenced block containing the Neoflow action JSON as your response "
            "in the final channel.  All tool dispatch is handled by the "
            "Neoflow runtime that reads this JSON block — never by Harmony's "
            "built-in function mechanism."
        )
        return content + harmony_note

    def clean_reply(self, text: str) -> str:
        """Strip Harmony channel headers and control tokens from a raw reply.

        Removes::

            <|start|>assistant<|channel|>analysis<|message|>
            <|start|>assistant<|channel|>final<|message|>
            <|start|>assistant<|channel|>commentary to=functions.x<|constrain|>json<|message|>
            <|end|>  <|call|>  <|return|>  <|constrain|>

        The remaining text (reasoning + JSON action block) is then safe to
        pass to ``parse_action`` and the agent display panel.
        """
        # 1. Strip full channel-header blocks (from <|start|> to <|message|>)
        text = self._CHANNEL_HEADER_RE.sub("\n", text)
        # 2. Strip any remaining bare Harmony control tokens
        text = self._BARE_TOKEN_RE.sub("", text)
        # 3. Collapse runs of blank lines left by stripping
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


class GLMProfile(ModelProfile):
    """Zhipu AI GLM-4 / GLM-4.7 / GLM-4.7-Flash models.

    GLM-4.7 uses the following raw sequence format::

        [gMASK]<sop><|system|>
        {system_content}<|user|>
        {user_content}<|assistant|>
        <think>

    Special tokens of note:
    - ``[gMASK]`` / ``<sop>``         — sequence start (added by the tokenizer)
    - ``<|system|>`` / ``<|user|>``   — role delimiters (applied via chat template)
    - ``<|assistant|>``               — assistant turn marker
    - ``<|observation|>``             — tool observation / function-call result
    - ``<think>`` / ``</think>``      — interleaved thinking / reasoning block
    - ``<|endoftext|>``               — stop token

    When served through Ollama or vLLM with a proper chat template, all of
    these tokens are injected automatically by the serving layer when it
    processes the standard ``{"role": "system", "content": "…"}`` message
    list.  No manual wrapping of the system prompt content is therefore
    needed.

    .. note::
        Running GLM-4.7 GGUFs through Ollama may have chat-template
        compatibility issues depending on the Ollama version and model file.
        If the model produces looping or garbled output, verify that Ollama
        is applying the correct chat template (``[gMASK]<sop>…`` sequence).

    This profile exists as a named, recognisable extension point so that
    future GLM-specific behaviour (e.g. toggling the thinking block via
    ``<think>`` injection, adjusting stop sequences) can be added here
    without touching any other file.
    """

    _PATTERNS: list[str] = [
        r"glm[-_.]?4",
        r"glm4",
    ]

    @property
    def name(self) -> str:
        return "glm"

    def matches(self, model_name: str) -> bool:
        lower = model_name.lower()
        return any(re.search(p, lower) for p in self._PATTERNS)


class DeepSeekProfile(ModelProfile):
    """DeepSeek instruct / chat models.

    DeepSeek models understand the standard OpenAI chat format; no extra
    wrapping is required.  This profile exists as an extension point.
    """

    _PATTERNS: list[str] = [
        r"deepseek",
    ]

    @property
    def name(self) -> str:
        return "deepseek"

    def matches(self, model_name: str) -> bool:
        lower = model_name.lower()
        return any(re.search(p, lower) for p in self._PATTERNS)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

# Ordered from most-specific to least-specific.  The first profile whose
# ``matches()`` returns True wins.  DefaultProfile must remain last.
_PROFILE_REGISTRY: list[ModelProfile] = [
    GPTOSSProfile(),
    LlamaInstructProfile(),
    QwenInstructProfile(),
    MistralInstructProfile(),
    GLMProfile(),
    DeepSeekProfile(),
    DefaultProfile(),  # fallback — must be last
]


def resolve_model_profile(model_name: str) -> ModelProfile:
    """Return the best :class:`ModelProfile` for *model_name*.

    Iterates :data:`_PROFILE_REGISTRY` in order and returns the first
    non-default profile that matches.  Falls back to :class:`DefaultProfile`
    when nothing else matches.

    Args:
        model_name: The model identifier string (e.g. ``"llama3.1:latest"``
                    or ``"gpt-4o-mini"``).

    Returns:
        A :class:`ModelProfile` instance (never ``None``).
    """
    for profile in _PROFILE_REGISTRY:
        if isinstance(profile, DefaultProfile):
            break  # reached the fallback — stop here
        if profile.matches(model_name):
            return profile
    return _PROFILE_REGISTRY[-1]  # DefaultProfile


def register_profile(profile: ModelProfile, *, position: int = 0) -> None:
    """Register a custom :class:`ModelProfile` into the global registry.

    Args:
        profile: The profile instance to register.
        position: Index at which to insert (0 = highest priority, before all
                  built-ins).  The :class:`DefaultProfile` at the end is never
                  displaced.
    """
    # Keep DefaultProfile pinned at the end
    insert_at = min(position, len(_PROFILE_REGISTRY) - 1)
    _PROFILE_REGISTRY.insert(insert_at, profile)
