"""Interactive input and cancellation support for the agent loop and chat."""

import contextvars
import re
import sys
import threading
import time
from concurrent.futures import Future

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.key_binding import KeyBindings
from rich.console import Console
from rich.panel import Panel

from neoflow.agent.domains import list_domains
from neoflow.status_bar import estimate_tokens, safe_console_print

# Global context variable to track the current active StatusBar instance
_active_status_bar: contextvars.ContextVar = contextvars.ContextVar(
    "_active_status_bar", default=None
)


def set_active_status_bar(bar) -> None:
    """Register the active StatusBar instance for pause/resume during prompts.
    
    Args:
        bar: The StatusBar instance, or None to unregister.
    """
    _active_status_bar.set(bar)


_MENTION_PATTERN = re.compile(r"@\w*")


class DomainCompleter(Completer):
    """Autocomplete @domain mentions from available domain prompt files."""

    def get_completions(self, document: Document, complete_event):
        word = document.get_word_before_cursor(pattern=_MENTION_PATTERN)
        if not word or not word.startswith("@"):
            return
        prefix = word[1:]  # strip the leading @
        for name in list_domains():
            if name.startswith(prefix):
                # Replace the entire @prefix with @name
                yield Completion(f"@{name}", start_position=-len(word))


class AgentCancelled(Exception):
    """Raised when the user cancels the agent loop (e.g. Ctrl+C during thinking)."""


def _make_multiline_bindings():
    """Create key bindings for multiline input.

    - If the text starts with ``/``, Enter submits immediately (slash commands).
    - Otherwise, Enter inserts a newline and a second Enter on a blank line submits.
    """
    kb = KeyBindings()

    @kb.add("enter")
    def _handle_enter(event):
        buf = event.current_buffer
        doc = buf.document
        text = doc.text

        # Slash commands: submit immediately on first Enter
        if text.strip().startswith("/"):
            buf.validate_and_handle()
            return

        # Current line is blank and buffer has content → submit
        if doc.current_line_before_cursor.strip() == "" and text.strip():
            cleaned = text.rstrip("\n").rstrip(" ")
            buf.text = cleaned
            buf.cursor_position = len(cleaned)
            buf.validate_and_handle()
        elif text.strip() == "":
            # Completely empty — do nothing
            pass
        else:
            buf.insert_text("\n")

    return kb


_bindings = _make_multiline_bindings()
_domain_completer = DomainCompleter()
_chat_session = PromptSession()
_agent_session = PromptSession(completer=_domain_completer, complete_while_typing=True)


def multiline_prompt(prompt_text: str, is_agent: bool = False) -> str:
    """Read multiline input. Enter adds newlines, empty line (Enter twice) submits.

    Args:
        prompt_text: The prompt prefix to display (e.g. "> " or "agent> ").
        is_agent: If True, uses the agent-specific session (separate history).

    Returns:
        The user's input string (may contain newlines).

    Raises:
        KeyboardInterrupt: If the user presses Ctrl+C.
        EOFError: If the user presses Ctrl+D.
    """
    session = _agent_session if is_agent else _chat_session
    
    # Pause any active status bar to allow prompt_toolkit to work without ANSI conflicts
    bar = _active_status_bar.get()
    if bar is not None:
        bar.pause()
    
    try:
        return session.prompt(
            HTML(prompt_text),
            multiline=True,
            key_bindings=_bindings,
        )
    finally:
        # Resume the status bar after input is complete
        if bar is not None:
            bar.resume()


def _agent_prompt_impl(
    message: str,
    choices: list[str] | None = None,
    default: str = "",
    console: Console | None = None,
    status_bar=None,
    modal_title: str | None = None,
    modal_body: str | None = None,
    modal_style: str = "cyan",
) -> str:
    """Internal prompt implementation with optional Rich modal rendering."""
    suffix = ""
    if choices:
        suffix = f" [{'/'.join(choices)}]"
    if default:
        suffix += f" ({default})"
    suffix += ": "

    if console is not None and choices:
        body = modal_body or f"[bold]{message}[/bold]"
        body += "\n\n" + "\n".join(f"• [bold]{choice}[/bold]" for choice in choices)
        if default:
            body += f"\n\n[dim]Default: {default}[/dim]"
        safe_console_print(
            console,
            status_bar,
            Panel(body, title=modal_title or "Action Required", border_style=modal_style),
        )

    # Pause the status bar once for the entire interaction to avoid ANSI conflicts
    # with prompt_toolkit. Pausing inside the retry loop would cause rapid
    # Live stop/start cycles (each writing escape sequences) that corrupt terminal state.
    bar = _active_status_bar.get()
    if bar is not None:
        bar.pause()
    try:
        while True:
            try:
                answer = _agent_session.prompt(HTML(f"<b>{message}</b>{suffix}")).strip()
            except (KeyboardInterrupt, EOFError):
                raise AgentCancelled()

            if not answer and default:
                return default
            if choices is None or answer in choices:
                return answer
    finally:
        if bar is not None:
            bar.resume()


def agent_prompt(
    message: str,
    choices: list[str] | None = None,
    default: str = "",
    console: Console | None = None,
    status_bar=None,
    modal_title: str | None = None,
    modal_body: str | None = None,
    modal_style: str = "cyan",
) -> str:
    """Prompt the user with readline-like editing (arrow keys, history).

    When ``choices`` is provided and a ``console`` is passed, the interaction
    message is shown in a Rich modal panel; only the short input line remains
    in terminal scroll.
    """
    return _agent_prompt_impl(
        message,
        choices=choices,
        default=default,
        console=console,
        status_bar=status_bar,
        modal_title=modal_title,
        modal_body=modal_body,
        modal_style=modal_style,
    )


def run_llm_with_cancel(llm_fn, status_bar=None):
    """Run *llm_fn()* in a background thread so Ctrl+C can cancel it.

    Polls the future with a short timeout so that KeyboardInterrupt is
    delivered to the main thread promptly.

    Args:
        llm_fn: A zero-argument callable that performs the LLM request.
        status_bar: Optional StatusBar instance. When provided, the inline
                    ANSI spinner is skipped (the status bar handles display).

    Returns:
        Whatever *llm_fn* returns.

    Raises:
        AgentCancelled: If the user presses Ctrl+C while waiting.
    """
    _FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    _LABEL = "Agent is thinking..."

    future: Future = Future()

    def _target():
        try:
            result = llm_fn()
            future.set_result(result)
        except Exception as exc:
            future.set_exception(exc)

    thread = threading.Thread(target=_target, daemon=True)
    thread.start()
    started_at = time.time()

    frame_idx = 0
    try:
        while True:
            if status_bar is None:
                # Draw inline spinner frame
                frame = f"\r\033[35m{_FRAMES[frame_idx % len(_FRAMES)]} {_LABEL}\033[0m"
                sys.stdout.write(frame)
                sys.stdout.flush()
                frame_idx += 1

            try:
                result = future.result(timeout=0.15)
                elapsed = max(time.time() - started_at, 0.001)
                if status_bar is not None:
                    completion_tokens = _extract_completion_tokens(result)
                    status_bar.add_tokens(completion_tokens)
                    status_bar.set_token_rate(completion_tokens / elapsed)
                if status_bar is None:
                    # Clear the spinner line before returning
                    sys.stdout.write(f"\r{' ' * (len(_LABEL) + 4)}\r")
                    sys.stdout.flush()
                return result
            except TimeoutError:
                continue
    except KeyboardInterrupt:
        llm_fn = None  # release closure reference to clean_messages
        if status_bar is None:
            sys.stdout.write(f"\r{' ' * (len(_LABEL) + 4)}\r")
            sys.stdout.flush()
        raise AgentCancelled()


def _extract_completion_tokens(response) -> int:
    """Best-effort extraction of completion token count from provider responses."""
    if not isinstance(response, dict):
        return 0

    usage = response.get("usage")
    if isinstance(usage, dict):
        for key in ("completion_tokens", "output_tokens", "eval_count"):
            value = usage.get(key)
            if isinstance(value, (int, float)) and value > 0:
                return int(value)

    for key in ("completion_tokens", "output_tokens", "eval_count"):
        value = response.get(key)
        if isinstance(value, (int, float)) and value > 0:
            return int(value)

    content = ""
    if "choices" in response and response["choices"]:
        choice = response["choices"][0]
        if isinstance(choice, dict):
            if isinstance(choice.get("message"), dict):
                content = choice["message"].get("content", "") or ""
            elif isinstance(choice.get("text"), str):
                content = choice["text"]
    elif isinstance(response.get("message"), dict):
        content = response["message"].get("content", "") or ""

    return estimate_tokens(content)
