"""Rich-only status bar rendering.

Keeps status display simple and avoids manual ANSI cursor/scroll manipulation.
"""

import sys
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field

from rich.console import Console
from rich.live import Live
from rich.text import Text

@dataclass
class StatusState:
    """Mutable state rendered by the status bar."""

    active: bool = False
    message: str = ""
    start_time: float = field(default_factory=time.time)
    message_count: int = 0
    token_count: int = 0
    token_rate: float = 0.0
    last_action: str = ""
    is_loading: bool = False
    # Task list: list of (description, status) where status is "pending" / "in_progress" / "done"
    tasks: list[tuple[str, str]] = field(default_factory=list)


_SPINNER_FRAMES = ["\u280b", "\u2819", "\u2839", "\u2838", "\u283c", "\u2834", "\u2826", "\u2827", "\u2807", "\u280f"]

class StatusBar:
    """A compact status line rendered via Rich Live."""

    def __init__(self, output_file=None, enabled: bool = True) -> None:
        """Initialize the status bar.
        
        Args:
            output_file: File object to write to (defaults to sys.stdout)
            enabled: Whether the status bar is enabled (set to False to disable completely)
        """
        self._state = StatusState()
        self._lock = threading.Lock()
        self._draw_lock = threading.RLock()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._frame_idx = 0
        self._paused = False
        self._suspend_count = 0
        self._output_file = output_file or sys.stdout
        self._console = Console(file=self._output_file)
        self._live: Live | None = None
        self._enabled = enabled

    # -- Public API: lifecycle ------------------------------------------------

    def start(self) -> None:
        """Activate the status bar and begin rendering."""
        if not self._enabled:
            return  # Do nothing if disabled
        
        # Register this instance as the active status bar for prompt pause/resume
        from neoflow.agent.input import set_active_status_bar
        set_active_status_bar(self)
        
        with self._lock:
            self._state.active = True
            self._state.start_time = time.time()
        self._start_live()
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Tear down the status bar and restore the terminal."""
        if not self._enabled:
            return  # Do nothing if disabled
        
        # Unregister this instance as the active status bar
        from neoflow.agent.input import set_active_status_bar
        set_active_status_bar(None)
        
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=1)
            self._thread = None
        with self._lock:
            self._state.active = False
        self._stop_live()

    def pause(self) -> None:
        """Pause status rendering (used during prompt input)."""
        self._paused = True
        self._stop_live()

    def resume(self) -> None:
        """Resume status rendering after a pause."""
        self._paused = False
        self._start_live()

    @contextmanager
    def suspend(self):
        """Temporarily suspend status bar rendering for safe normal output writes."""
        with self._lock:
            self._suspend_count += 1
        # Wait for any in-flight draw to finish before yielding.
        with self._draw_lock:
            pass
        try:
            yield
        finally:
            with self._lock:
                self._suspend_count = max(0, self._suspend_count - 1)

    # -- Public API: state setters -------------------------------------------

    def set_message(self, message: str) -> None:
        with self._lock:
            self._state.message = message

    def set_loading(self, loading: bool, message: str = "") -> None:
        with self._lock:
            self._state.is_loading = loading
            if message:
                self._state.message = message

    def set_last_action(self, action: str) -> None:
        with self._lock:
            self._state.last_action = action

    def increment_messages(self, count: int = 1) -> None:
        with self._lock:
            self._state.message_count += count

    def add_tokens(self, tokens: int) -> None:
        with self._lock:
            self._state.token_count += tokens

    def set_token_rate(self, tokens_per_second: float) -> None:
        with self._lock:
            self._state.token_rate = max(0.0, tokens_per_second)

    # -- Public API: task list -----------------------------------------------

    def set_tasks(self, tasks: list[tuple[str, str]]) -> None:
        """Set the full task list. Each entry is (description, status)."""
        with self._lock:
            self._state.tasks = list(tasks)

    def start_task(self, index: int) -> None:
        """Mark a task as in_progress."""
        with self._lock:
            if 0 <= index < len(self._state.tasks):
                desc, _ = self._state.tasks[index]
                self._state.tasks[index] = (desc, "in_progress")

    def complete_task(self, index: int) -> None:
        """Mark a task as done."""
        with self._lock:
            if 0 <= index < len(self._state.tasks):
                desc, _ = self._state.tasks[index]
                self._state.tasks[index] = (desc, "done")

    # -- Internal: task progress summary -------------------------------------

    def _task_progress_summary(self, tasks: list[tuple[str, str]], max_len: int = 80) -> str:
        """Return compact task progress text: ``current/total - description``."""
        if not tasks:
            return ""

        total = len(tasks)
        current_idx = None

        for i, (_, status) in enumerate(tasks):
            if status == "in_progress":
                current_idx = i
                break

        if current_idx is None:
            for i, (_, status) in enumerate(tasks):
                if status != "done":
                    current_idx = i
                    break

        if current_idx is None:
            current_idx = total - 1

        desc, _ = tasks[current_idx]
        progress = f"{current_idx + 1}/{total} - "
        max_desc = max(0, max_len - len(progress))
        if max_desc and len(desc) > max_desc:
            desc = desc[: max_desc - 3] + "..."

        return f"{progress}{desc}"

    def _start_live(self) -> None:
        """Start Rich live rendering if active and not paused."""
        with self._lock:
            should_start = self._state.active and not self._paused and self._enabled
        if not should_start:
            return

        with self._draw_lock:
            if self._live is None:
                self._live = Live(
                    Text(""),
                    console=self._console,
                    refresh_per_second=5,
                    auto_refresh=False,
                    transient=True,
                )
                self._live.start()

    def _stop_live(self) -> None:
        """Stop Rich live rendering if currently running."""
        with self._draw_lock:
            if self._live is not None:
                self._live.stop()
                self._live = None

    # -- Render loop ---------------------------------------------------------

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            with self._lock:
                is_suspended = self._suspend_count > 0
            if not self._paused and not is_suspended:
                try:
                    self._render()
                except Exception:
                    pass
            self._stop_event.wait(0.2)

    def _render(self) -> None:
        with self._lock:
            state = StatusState(
                active=self._state.active,
                message=self._state.message,
                start_time=self._state.start_time,
                message_count=self._state.message_count,
                token_count=self._state.token_count,
                token_rate=self._state.token_rate,
                last_action=self._state.last_action,
                is_loading=self._state.is_loading,
                tasks=list(self._state.tasks),
            )

        if not state.active:
            return

        parts = []
        task_summary = self._task_progress_summary(state.tasks, max_len=90)
        if task_summary:
            parts.append(task_summary)

        if state.is_loading and state.message:
            frame = _SPINNER_FRAMES[self._frame_idx % len(_SPINNER_FRAMES)]
            self._frame_idx += 1
            parts.append(f"{frame} {state.message}")
        elif state.message:
            parts.append(f"● {state.message}")

        elapsed = time.time() - state.start_time
        mins, secs = divmod(int(elapsed), 60)
        parts.append(f"{mins}:{secs:02d}")
        parts.append(f"msgs: {state.message_count}")
        token_str = _format_tokens(state.token_count)
        parts.append(f"tokens: ~{token_str}")
        if state.token_rate > 0:
            parts.append(f"tok/s: {state.token_rate:.1f}")
        if state.last_action:
            parts.append(f"last: {state.last_action}")

        status_line = "  |  ".join(parts) if parts else ""
        renderable = Text(status_line, overflow="ellipsis", no_wrap=True)

        with self._draw_lock:
            if self._live is None and not self._paused:
                self._start_live()
            if self._live is not None:
                self._live.update(renderable, refresh=True)


def _format_tokens(count: int) -> str:
    """Format a token count as a human-readable string (e.g. 2.1k)."""
    if count < 1000:
        return str(count)
    elif count < 100_000:
        return f"{count / 1000:.1f}k"
    else:
        return f"{count / 1000:.0f}k"


def estimate_tokens(text: str) -> int:
    """Rough token estimate: max of char/4 and word count.

    Works reasonably (~10-20% accuracy) for LLaMA/Qwen/GLM tokenizers
    without any external dependency.
    """
    if not text:
        return 0
    return max(len(text) // 4, len(text.split()))


@contextmanager
def status_context(bar: "StatusBar", message: str):
    """Context manager that sets loading state on entry and clears on exit."""
    bar.set_loading(True, message)
    try:
        yield bar
    finally:
        bar.set_loading(False)


@contextmanager
def status_output_guard(bar: "StatusBar | None"):
    """Guard terminal output so status bar redraws cannot interleave with prints."""
    if bar is None:
        yield
        return

    with bar.suspend():
        yield


def safe_console_print(console, bar: "StatusBar | None", *args, **kwargs) -> None:
    """Print to a Rich console while guarding against status bar draw races."""
    with status_output_guard(bar):
        if bar is not None and getattr(bar, "_live", None) is not None:
            bar._live.console.print(*args, **kwargs)
        else:
            console.print(*args, **kwargs)
