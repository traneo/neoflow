"""Persistent bottom status bar using ANSI scroll regions.

Reserves the bottom lines of the terminal for a status display (and optional
task list) while allowing normal Rich console output to scroll above it.
"""

import os
import signal
import sys
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field

_MAX_VISIBLE_TASKS = 6

@dataclass
class StatusState:
    """Mutable state rendered by the status bar."""

    active: bool = False
    message: str = ""
    start_time: float = field(default_factory=time.time)
    message_count: int = 0
    token_count: int = 0
    last_action: str = ""
    is_loading: bool = False
    # Task list: list of (description, status) where status is "pending" / "in_progress" / "done"
    tasks: list[tuple[str, str]] = field(default_factory=list)


_SPINNER_FRAMES = ["\u280b", "\u2819", "\u2839", "\u2838", "\u283c", "\u2834", "\u2826", "\u2827", "\u2807", "\u280f"]

_TASK_SYMBOLS = {
    "done": "\033[32m\u2713\033[0m",       # green checkmark
    "in_progress": "\033[33m\u25cf\033[0m", # yellow filled circle
    "pending": "\033[90m\u25cb\033[0m",     # dim open circle
}


class StatusBar:
    """A persistent status bar pinned to the bottom of the terminal.

    Uses ANSI scroll region escape sequences so that normal output (including
    Rich panels, tables, etc.) scrolls within the region above the bar.
    A background thread redraws the bar every 200 ms.

    When a task list is active, the reserved area expands to include task lines
    above the separator + status line.
    """

    def __init__(self, output_file=None, enabled: bool = True) -> None:
        """Initialize the status bar.
        
        Args:
            output_file: File object to write to (defaults to sys.stdout)
            enabled: Whether the status bar is enabled (set to False to disable completely)
        """
        self._state = StatusState()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._frame_idx = 0
        self._prev_sigwinch = None
        self._paused = False
        self._output_file = output_file or sys.stdout
        self._enabled = enabled

    # -- Public API: lifecycle ------------------------------------------------

    def start(self) -> None:
        """Activate the status bar and begin rendering."""
        if not self._enabled:
            return  # Do nothing if disabled
        with self._lock:
            self._state.active = True
            self._state.start_time = time.time()
        self._setup_scroll_region()
        self._install_sigwinch()
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Tear down the status bar and restore the terminal."""
        if not self._enabled:
            return  # Do nothing if disabled
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=1)
            self._thread = None
        with self._lock:
            self._state.active = False
        self._restore_scroll_region()
        self._uninstall_sigwinch()

    def pause(self) -> None:
        """Temporarily restore full scroll region (for prompt_toolkit)."""
        self._paused = True
        self._restore_scroll_region()

    def resume(self) -> None:
        """Re-establish the scroll region after a pause."""
        self._paused = False
        self._setup_scroll_region()

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

    # -- Public API: task list -----------------------------------------------

    def set_tasks(self, tasks: list[tuple[str, str]]) -> None:
        """Set the full task list. Each entry is (description, status)."""
        with self._lock:
            self._state.tasks = list(tasks)
        # Re-setup scroll region to account for new height
        if not self._paused:
            self._setup_scroll_region()

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

    # -- Internal: visible task window ---------------------------------------

    def _visible_tasks(self, tasks: list[tuple[str, str]]) -> list[tuple[str, str]]:
        """Return the rolling window of up to _MAX_VISIBLE_TASKS tasks."""
        if len(tasks) <= _MAX_VISIBLE_TASKS:
            return tasks

        # Find the first non-done task (or last task)
        first_active = len(tasks) - 1
        for i, (_, status) in enumerate(tasks):
            if status != "done":
                first_active = i
                break

        # Show some context: keep at least 1 completed task visible
        start = max(0, first_active - 1)
        # But don't go past the end
        if start + _MAX_VISIBLE_TASKS > len(tasks):
            start = max(0, len(tasks) - _MAX_VISIBLE_TASKS)

        return tasks[start : start + _MAX_VISIBLE_TASKS]

    def _reserved_lines(self) -> int:
        """Number of terminal lines reserved at the bottom."""
        with self._lock:
            tasks = list(self._state.tasks)
        visible = self._visible_tasks(tasks)
        # 2 base lines (separator + status) + visible task count
        return 2 + len(visible)

    # -- Scroll region helpers -----------------------------------------------

    @staticmethod
    def _get_terminal_size() -> tuple[int, int]:
        try:
            cols, rows = os.get_terminal_size()
        except OSError:
            cols, rows = 80, 24
        return cols, rows

    def _setup_scroll_region(self) -> None:
        """Set the scroll region to exclude the reserved bottom lines."""
        cols, rows = self._get_terminal_size()
        reserved = self._reserved_lines()
        scroll_bottom = rows - reserved
        if scroll_bottom < 1:
            scroll_bottom = 1
        self._output_file.write(f"\033[1;{scroll_bottom}r")
        self._output_file.write(f"\033[{scroll_bottom};1H")
        self._output_file.flush()

    def _restore_scroll_region(self) -> None:
        """Restore the full terminal scroll region and clear reserved lines."""
        cols, rows = self._get_terminal_size()
        reserved = self._reserved_lines()
        # Restore full scroll region
        self._output_file.write(f"\033[1;{rows}r")
        # Clear all reserved lines
        for i in range(reserved):
            self._output_file.write(f"\033[{rows - i};1H\033[2K")
        # Move cursor back up
        scroll_bottom = rows - reserved
        if scroll_bottom < 1:
            scroll_bottom = 1
        self._output_file.write(f"\033[{scroll_bottom};1H")
        self._output_file.flush()

    # -- SIGWINCH handling ---------------------------------------------------

    def _install_sigwinch(self) -> None:
        try:
            self._prev_sigwinch = signal.getsignal(signal.SIGWINCH)
            signal.signal(signal.SIGWINCH, self._handle_sigwinch)
        except (OSError, AttributeError, ValueError):
            pass  # Not available on this platform / not main thread

    def _uninstall_sigwinch(self) -> None:
        try:
            if self._prev_sigwinch is not None:
                signal.signal(signal.SIGWINCH, self._prev_sigwinch)
                self._prev_sigwinch = None
        except (OSError, AttributeError, ValueError):
            pass

    def _handle_sigwinch(self, signum, frame):
        if not self._paused:
            self._setup_scroll_region()
            self._render()
        if self._prev_sigwinch and callable(self._prev_sigwinch):
            self._prev_sigwinch(signum, frame)

    # -- Render loop ---------------------------------------------------------

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            if not self._paused:
                try:
                    self._render()
                except Exception:
                    pass
            self._stop_event.wait(0.2)

    def _render(self) -> None:
        cols, rows = self._get_terminal_size()

        with self._lock:
            state = StatusState(
                active=self._state.active,
                message=self._state.message,
                start_time=self._state.start_time,
                message_count=self._state.message_count,
                token_count=self._state.token_count,
                last_action=self._state.last_action,
                is_loading=self._state.is_loading,
                tasks=list(self._state.tasks),
            )

        if not state.active:
            return

        # -- Build task lines --
        visible_tasks = self._visible_tasks(state.tasks)
        task_lines: list[str] = []
        for desc, status in visible_tasks:
            symbol = _TASK_SYMBOLS.get(status, _TASK_SYMBOLS["pending"])
            # Truncate description to fit
            max_desc = cols - 6
            if len(desc) > max_desc:
                desc = desc[: max_desc - 3] + "..."
            task_lines.append(f"  {symbol} {desc}")

        # -- Build status line --
        parts = []
        if state.is_loading and state.message:
            frame = _SPINNER_FRAMES[self._frame_idx % len(_SPINNER_FRAMES)]
            self._frame_idx += 1
            parts.append(f" \033[35m{frame} {state.message}\033[0m")
        elif state.message:
            parts.append(f" \033[32m\u25cf {state.message}\033[0m")

        elapsed = time.time() - state.start_time
        mins, secs = divmod(int(elapsed), 60)
        parts.append(f"\033[36m{mins}:{secs:02d}\033[0m")
        parts.append(f"\033[33mmsgs: {state.message_count}\033[0m")
        token_str = _format_tokens(state.token_count)
        parts.append(f"\033[33mtokens: ~{token_str}\033[0m")
        if state.last_action:
            parts.append(f"\033[34mlast: {state.last_action}\033[0m")

        status_line = "  |  ".join(parts)
        separator = "\033[90m" + "\u2500" * cols + "\033[0m"

        # -- Draw everything --
        # Layout from bottom: row=rows is status, rows-1 is separator,
        # rows-2..rows-1-len(task_lines) are task lines
        reserved = 2 + len(task_lines)
        task_area_start = rows - reserved + 1  # first task line row

        out = "\0337"  # Save cursor
        # Draw task lines
        for i, tline in enumerate(task_lines):
            out += f"\033[{task_area_start + i};1H\033[2K{tline}"
        # Separator
        out += f"\033[{rows - 1};1H\033[2K{separator}"
        # Status line
        out += f"\033[{rows};1H\033[2K{status_line}"
        out += "\0338"  # Restore cursor

        self._output_file.write(out)
        self._output_file.flush()


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
