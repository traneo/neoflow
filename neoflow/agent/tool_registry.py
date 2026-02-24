"""Tool registry for NeoFlow agent — central registry for all agent tools.

Built-in tools are registered at startup. Tool packs (installed via
`neoflow tool install`) extend the registry with additional tools at runtime.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import os
import re
import shlex
import subprocess
import sys
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from neoflow.config import Config

logger = logging.getLogger(__name__)

# Valid tool name pattern: starts with lowercase letter, rest are lowercase/digits/underscore
_TOOL_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


# ---------------------------------------------------------------------------
# ToolDefinition abstract base class
# ---------------------------------------------------------------------------


class ToolDefinition(ABC):
    """Abstract base for all agent tools.

    Subclasses must set class-level attributes and implement ``execute()``.
    """

    name: str
    label: str
    icon: str
    description: str  # Markdown fragment injected into the system prompt
    security_level: Literal["safe", "approval", "unsafe"] = "safe"
    primary_param: str | None = None

    @abstractmethod
    def execute(self, action: dict, config: "Config", **ctx) -> str:
        """Execute the action and return a result string.

        Args:
            action: Parsed action dict from the LLM response.
            config: Application configuration.
            **ctx: Optional context keys — ``console``, ``status_bar``,
                   ``pre_completed``.
        """
        ...


# ---------------------------------------------------------------------------
# Shared private utilities (used by built-in tool implementations)
# ---------------------------------------------------------------------------


def _safe_path(path: str) -> tuple[Path, str | None]:
    """Resolve *path* and verify it is inside the working directory.

    Returns ``(resolved, None)`` on success or ``(resolved, error_message)``
    on failure.
    """
    cwd = Path(os.getcwd()).resolve()
    resolved = (cwd / path).resolve()
    try:
        resolved.relative_to(cwd)
    except ValueError:
        return resolved, f"Error: path '{path}' is outside the working directory."
    return resolved, None


def _get_notebook_path() -> str:
    """Return the absolute path to the agent notebook file."""
    from neoflow.init import NEOFLOW_DIR

    return os.path.join(os.getcwd(), NEOFLOW_DIR, "agent_notebook.md")


# ---------------------------------------------------------------------------
# Built-in tool implementations
# ---------------------------------------------------------------------------


class RunCommandTool(ToolDefinition):
    name = "run_command"
    label = "Run Command"
    icon = "💻"
    security_level = "approval"
    primary_param = "command"
    description = """\
### run_command
Execute a shell command and capture output (30-second timeout).
```json
{"action": "run_command", "command": "python -m pytest tests/"}
```
**Safety:** Never run destructive commands (rm -rf, system modifications). Use non-interactive modes for CLI tools."""

    def execute(self, action: dict, config: "Config", **ctx) -> str:
        command = action["command"]
        if "--break-system-packages" in command.lower():
            return (
                "COMMAND BLOCKED: '--break-system-packages' is prohibited "
                "and cannot be used in any mode."
            )
        if config.agent.unsafe_mode:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=os.getcwd(),
            )
        else:
            args = shlex.split(command)
            result = subprocess.run(
                args,
                shell=False,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=os.getcwd(),
            )
        stdout = result.stdout or ""
        stderr = result.stderr or ""
        if result.returncode != 0:
            parts = [f"COMMAND FAILED (exit code: {result.returncode})"]
            if stdout:
                parts.append(f"STDOUT:\n{stdout.rstrip()}")
            if stderr:
                parts.append(f"STDERR:\n{stderr.rstrip()}")
            return "\n".join(parts)
        output = stdout
        if stderr:
            output += ("\n" if output else "") + f"STDERR:\n{stderr}"
        return output or "(no output)"


class WriteFileTool(ToolDefinition):
    name = "write_file"
    label = "Write File"
    icon = "✍️"
    security_level = "safe"
    primary_param = "path"
    description = """\
### write_file
Create or overwrite a file with the given content. Parent directories are created automatically.
```json
{"action": "write_file", "path": "src/utils/helpers.py", "content": "def greet(name):\\n    return f\\"Hello, {name}!\\"\\n"}
```
**Required:** `path` (relative to workspace root), `content` (the full file text)"""

    def execute(self, action: dict, config: "Config", **ctx) -> str:
        path = action["path"]
        content = action["content"]
        resolved, err = _safe_path(path)
        if err:
            return err
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content)
        lines = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
        return f"File written: {path} ({resolved.stat().st_size} bytes, {lines} lines)"


class ReadFileTool(ToolDefinition):
    name = "read_file"
    label = "Read File"
    icon = "📖"
    security_level = "safe"
    primary_param = "path"
    description = """\
### read_file
Read a file and return its content with line numbers.
```json
{"action": "read_file", "path": "src/utils/helpers.py"}
```
**Optional:** `offset` (first line to return, 0-based, default 0), `limit` (max lines to return, default 200)
**Use when:** You need to inspect a file before editing, or verify a write succeeded."""

    def execute(self, action: dict, config: "Config", **ctx) -> str:
        path = action["path"]
        offset = action.get("offset", 0)
        limit = action.get("limit", 200)
        resolved, err = _safe_path(path)
        if err:
            return err
        if not resolved.is_file():
            return f"Error: file not found: {path}"
        lines = resolved.read_text(errors="replace").splitlines(keepends=True)
        total = len(lines)
        chunk = lines[offset : offset + limit]
        numbered = "".join(f"{offset + i + 1:4}: {line}" for i, line in enumerate(chunk))
        remaining = total - offset - len(chunk)
        suffix = (
            f"\n[{remaining} more lines — use offset={offset + limit} to continue]"
            if remaining > 0
            else ""
        )
        return f"File: {path} ({total} lines)\n{numbered}{suffix}"


class EditFileTool(ToolDefinition):
    name = "edit_file"
    label = "Edit File"
    icon = "🖊️"
    security_level = "safe"
    primary_param = "path"
    description = """\
### edit_file
Replace an exact substring in a file with new text. The `old_string` must appear **exactly once** — if it appears multiple times, add more surrounding lines to make it unique.
```json
{"action": "edit_file", "path": "src/utils/helpers.py", "old_string": "def greet(name):\\n    return f\\"Hello, {name}!\\"\\n", "new_string": "def greet(name: str) -> str:\\n    return f\\"Hi, {name}!\\"\\n"}
```
**Required:** `path`, `old_string` (exact text to replace), `new_string` (replacement text)
**Tip:** Always `read_file` first so you can copy the exact whitespace and indentation into `old_string`."""

    def execute(self, action: dict, config: "Config", **ctx) -> str:
        path = action["path"]
        old_string = action["old_string"]
        new_string = action["new_string"]
        resolved, err = _safe_path(path)
        if err:
            return err
        if not resolved.is_file():
            return f"Error: file not found: {path}"
        content = resolved.read_text(errors="replace")
        count = content.count(old_string)
        if count == 0:
            return (
                f"Error: old_string not found in {path}. "
                "Verify exact whitespace and indentation — use read_file to inspect the file first."
            )
        if count > 1:
            return (
                f"Error: old_string found {count} times in {path}. "
                "Add more surrounding context to make it unique."
            )
        resolved.write_text(content.replace(old_string, new_string, 1))
        return f"File edited: {path}"


class DeleteFileTool(ToolDefinition):
    name = "delete_file"
    label = "Delete File"
    icon = "🗑️"
    security_level = "safe"
    primary_param = "path"
    description = """\
### delete_file
Delete a single file.
```json
{"action": "delete_file", "path": "src/utils/old_helpers.py"}
```
**Required:** `path`"""

    def execute(self, action: dict, config: "Config", **ctx) -> str:
        path = action["path"]
        resolved, err = _safe_path(path)
        if err:
            return err
        if not resolved.exists():
            return f"Error: file not found: {path}"
        if not resolved.is_file():
            return f"Error: '{path}' is a directory, not a file."
        resolved.unlink()
        return f"File deleted: {path}"


class SearchCodeTool(ToolDefinition):
    name = "search_code"
    label = "Search Code"
    icon = "🔎"
    security_level = "safe"
    primary_param = "query"
    description = """\
### search_code
Hybrid semantic + keyword search over indexed code snippets.
```json
{"action": "search_code", "query": "authentication middleware", "limit": 5, "repository": "backend-api", "language": "python"}
```
**Optional filters:**
- `limit`: 1-10 results (default: 5)
- `repository`: Filter by specific repo name
- `language`: Filter by programming language (python, javascript, etc.)
- `is_test`: Boolean to include/exclude test files
- `directory`: Filter by directory path"""

    def execute(self, action: dict, config: "Config", **ctx) -> str:
        from neoflow.search.tools import search_code

        return search_code(
            action["query"],
            config,
            limit=action.get("limit", 5),
            repository=action.get("repository"),
            language=action.get("language"),
            is_test=action.get("is_test"),
            directory=action.get("directory"),
        )


class SearchDocumentationTool(ToolDefinition):
    name = "search_documentation"
    label = "Search Documentation"
    icon = "📚"
    security_level = "safe"
    primary_param = "query"
    description = """\
### search_documentation
Hybrid semantic + keyword search over indexed documentation.
```json
{"action": "search_documentation", "query": "API authentication setup", "limit": 5}
```
**Optional:** `limit` 1-10 (default: 5)"""

    def execute(self, action: dict, config: "Config", **ctx) -> str:
        from neoflow.search.tools import search_documentation

        return search_documentation(
            action["query"],
            config,
            limit=action.get("limit", 5),
        )


class SearchTicketsTool(ToolDefinition):
    name = "search_tickets"
    label = "Search Tickets"
    icon = "🎫"
    security_level = "safe"
    primary_param = "query"
    description = """\
### search_tickets
Search support tickets by keyword. Returns ticket summaries with top relevant comments.
```json
{"action": "search_tickets", "query": "payment gateway timeout", "limit": 10}
```
**Optional:** `limit` 1-20 (default: 10)
**Returns:** Ticket title, question, URL, and top relevant comments for each match"""

    def execute(self, action: dict, config: "Config", **ctx) -> str:
        from neoflow.search.tools import search_tickets

        return search_tickets(
            action["query"],
            config,
            limit=action.get("limit", 10),
        )


class AskChatTool(ToolDefinition):
    name = "ask_chat"
    label = "Ask Chat"
    icon = "💬"
    security_level = "safe"
    primary_param = "query"
    description = """\
### ask_chat
Delegate complex research questions to the chat assistant. It searches tickets, code, documentation, and files.
```json
{"action": "ask_chat", "query": "How is authentication implemented in the payment service?"}
```
**Use when:** You need comprehensive research across multiple data sources or domain knowledge."""

    def execute(self, action: dict, config: "Config", **ctx) -> str:
        from neoflow.chat import run_chat

        console = ctx.get("console")
        status_bar = ctx.get("status_bar")
        answer = run_chat(action["query"], config, console, status_bar, silent=True)
        return answer or "Chat could not produce an answer."


class AskUserTool(ToolDefinition):
    name = "ask_user"
    label = "Ask User"
    icon = "🙋"
    security_level = "safe"
    primary_param = "question"
    description = """\
### ask_user
Ask the human user for missing information, decisions, or conflict resolution.
```json
{"action": "ask_user", "question": "Which environment should I target?", "options": ["staging", "production"], "allow_freeform": true}
```
**Use when:** Requirements are ambiguous, information is missing, or two valid options conflict and user input is needed.
**Optional fields:**
- `options`: list of suggested answer choices
- `allow_freeform`: whether user can provide a custom answer (default: `true`)"""

    def execute(self, action: dict, config: "Config", **ctx) -> str:
        from neoflow.agent.input import agent_prompt
        from neoflow.status_bar import safe_console_print as _safe_print
        from rich.panel import Panel

        question = action["question"]
        options = action.get("options")
        allow_freeform = action.get("allow_freeform", True)
        console = ctx.get("console")
        status_bar = ctx.get("status_bar")
        normalized_options = [str(opt) for opt in (options or []) if str(opt).strip()]

        if console is not None:
            body = f"[bold]{question}[/bold]"
            if normalized_options:
                option_lines = [f"[{idx}] {opt}" for idx, opt in enumerate(normalized_options, 1)]
                body += "\n\n" + "\n".join(option_lines)
                if allow_freeform:
                    body += "\n[f] Enter a custom response"
            _safe_print(console, status_bar)
            _safe_print(
                console,
                status_bar,
                Panel(body, title="Agent Needs User Input", border_style="cyan"),
            )

        if normalized_options:
            choices = [str(idx) for idx in range(1, len(normalized_options) + 1)]
            default_choice = choices[0] if choices else ""
            if allow_freeform:
                choices.append("f")
            selection = agent_prompt(
                "Choose an option",
                choices=choices,
                default=default_choice,
            )
            if selection == "f":
                response = agent_prompt("Your response")
                response_type = "freeform"
            else:
                response = normalized_options[int(selection) - 1]
                response_type = f"option_{selection}"
        else:
            response = agent_prompt("Your response")
            response_type = "freeform"

        return (
            "User response received.\n"
            f"Question: {question}\n"
            f"Response type: {response_type}\n"
            f"Response: {response}"
        )


class NotebookSearchTool(ToolDefinition):
    name = "notebook_search"
    label = "Notebook Search"
    icon = "🔖"
    security_level = "safe"
    primary_param = "query"
    description = """\
### notebook_search
Search notebook entries for keywords or patterns.
```json
{"action": "notebook_search", "query": "docker compose"}
```"""

    def execute(self, action: dict, config: "Config", **ctx) -> str:
        notebook_path = _get_notebook_path()
        query = action["query"]
        if not os.path.isfile(notebook_path):
            return "No agent notebook found. Run /init to create one."
        with open(notebook_path) as f:
            content = f.read()
        entries = re.split(r"(?=^## )", content, flags=re.MULTILINE)
        matches = []
        for entry in entries:
            entry = entry.strip()
            if not entry or not entry.startswith("## "):
                continue
            try:
                if re.search(query, entry, re.IGNORECASE):
                    matches.append(entry)
            except re.error:
                if query.lower() in entry.lower():
                    matches.append(entry)
        if not matches:
            return f"No notebook entries matching '{query}'."
        return "\n\n".join(matches)


class NotebookAddTool(ToolDefinition):
    name = "notebook_add"
    label = "Notebook Add"
    icon = "📝"
    security_level = "safe"
    primary_param = "title"
    description = """\
### notebook_add
Add a new entry to preserve knowledge for future tasks.
```json
{"action": "notebook_add", "title": "Docker Compose Dev Setup", "content": "Working command: docker-compose -f docker-compose.dev.yml up -d\\n\\nNote: Requires .env file with API_KEY set."}
```
**When to use:** After discovering a working solution through trial and error, or learning important project-specific patterns."""

    def execute(self, action: dict, config: "Config", **ctx) -> str:
        notebook_path = _get_notebook_path()
        if not os.path.isfile(notebook_path):
            return "No agent notebook found. Run /init to create one."
        entry = f"\n\n## {action['title']}\n\n{action['content']}\n"
        with open(notebook_path, "a") as f:
            f.write(entry)
        return f"Added notebook entry: {action['title']}"


class NotebookRemoveTool(ToolDefinition):
    name = "notebook_remove"
    label = "Notebook Remove"
    icon = "🗑️"
    security_level = "safe"
    primary_param = "title"
    description = """\
### notebook_remove
Remove an outdated or incorrect entry by exact title.
```json
{"action": "notebook_remove", "title": "Docker Compose Dev Setup"}
```"""

    def execute(self, action: dict, config: "Config", **ctx) -> str:
        notebook_path = _get_notebook_path()
        title = action["title"]
        if not os.path.isfile(notebook_path):
            return "No agent notebook found. Run /init to create one."
        with open(notebook_path) as f:
            content = f.read()
        parts = re.split(r"(?=^## )", content, flags=re.MULTILINE)
        found = False
        kept = []
        for part in parts:
            stripped = part.strip()
            if stripped.startswith("## "):
                heading = stripped.splitlines()[0].removeprefix("## ").strip()
                if heading == title:
                    found = True
                    continue
            kept.append(part)
        if not found:
            return f"No notebook entry with title '{title}' found."
        with open(notebook_path, "w") as f:
            f.write("".join(kept))
        return f"Removed notebook entry: {title}"


class MarkTaskDoneTool(ToolDefinition):
    name = "mark_task_done"
    label = "Mark Task Done"
    icon = "☑️"
    security_level = "safe"
    primary_param = "task_id"
    description = """\
### mark_task_done
Signal that a future task has already been completed as a side-effect of the current task.
The framework will skip that task automatically when it is reached, recording your summary as its resolution.
```json
{"action": "mark_task_done", "task_id": "task_3", "summary": "Auth middleware was created in src/middleware/auth.py while implementing task_2."}
```
**Required:** `task_id` — the ID shown in the "Remaining after this" list (e.g. `task_2`, `task_3`).
**Required:** `summary` — what was accomplished; becomes the official resolution for that task.
**Use when:** While completing your current task you have incidentally implemented what a later task requires.
Do not call this speculatively — only when the work is genuinely finished and verified."""

    def execute(self, action: dict, config: "Config", **ctx) -> str:
        task_id = action.get("task_id", "").strip()
        summary = action.get("summary", "Completed as part of this task.")
        pre_completed = ctx.get("pre_completed")
        if not task_id:
            return "Error: mark_task_done requires a 'task_id' field."
        if pre_completed is None:
            return "Error: mark_task_done is only available in multi-task workflows."
        pre_completed[task_id] = summary
        logger.info("Task '%s' marked done ahead of schedule.", task_id)
        return f"Task '{task_id}' recorded as already done. It will be skipped when reached."


# ---------------------------------------------------------------------------
# Reserved names and built-in instances
# ---------------------------------------------------------------------------

#: Tool names that cannot be overridden by external tool packs.
RESERVED_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "run_command",
        "write_file",
        "read_file",
        "edit_file",
        "delete_file",
        "search_code",
        "search_documentation",
        "search_tickets",
        "ask_chat",
        "ask_user",
        "notebook_search",
        "notebook_add",
        "notebook_remove",
        "mark_task_done",
        "done",
    }
)

# All built-in tool instances, in display order
_BUILTIN_TOOLS: list[ToolDefinition] = [
    AskChatTool(),
    AskUserTool(),
    RunCommandTool(),
    WriteFileTool(),
    ReadFileTool(),
    EditFileTool(),
    DeleteFileTool(),
    SearchCodeTool(),
    SearchDocumentationTool(),
    SearchTicketsTool(),
    NotebookSearchTool(),
    NotebookAddTool(),
    NotebookRemoveTool(),
    MarkTaskDoneTool(),
]


# ---------------------------------------------------------------------------
# ToolRegistry
# ---------------------------------------------------------------------------


class ToolRegistry:
    """Central registry for all agent tools (built-in + installed packs)."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}
        for tool in _BUILTIN_TOOLS:
            self._tools[tool.name] = tool

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register(self, tool: ToolDefinition) -> None:
        """Register an external tool.

        Raises:
            ValueError: If the name is invalid or clashes with a reserved name.
        """
        if not _TOOL_NAME_PATTERN.match(tool.name):
            raise ValueError(
                f"Tool name '{tool.name}' is invalid. Must match [a-z][a-z0-9_]*"
            )
        if tool.name in RESERVED_TOOL_NAMES:
            raise ValueError(
                f"Tool name '{tool.name}' is reserved by a built-in tool and cannot be overridden."
            )
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolDefinition | None:
        """Return the tool with the given name, or ``None`` if not registered."""
        return self._tools.get(name)

    def all_names(self) -> set[str]:
        """Return all registered tool names, excluding the special ``done`` action."""
        return {name for name in self._tools if name != "done"}

    def generate_prompt_section(self) -> str:
        """Generate the ``# Available Actions`` section injected into the system prompt."""
        parts: list[str] = ["# Available Actions"]

        def _tool_desc(name: str) -> str:
            t = self._tools.get(name)
            return t.description if t else ""

        # Exploration & Research
        expl = [n for n in ("ask_chat", "ask_user") if n in self._tools]
        if expl:
            parts.append("\n## Exploration & Research\n")
            for n in expl:
                parts.append(_tool_desc(n))

        # Execution
        exec_ = [n for n in ("run_command",) if n in self._tools]
        if exec_:
            parts.append("\n## Execution\n")
            for n in exec_:
                parts.append(_tool_desc(n))

        # File Operations
        file_ops = [
            n
            for n in ("write_file", "read_file", "edit_file", "delete_file")
            if n in self._tools
        ]
        if file_ops:
            parts.append("\n## File Operations\n")
            parts.append(
                "Use these tools for all file creation, reading, editing, and deletion. "
                "They are more reliable than embedding file content inside shell commands "
                "because they require only standard JSON string escaping.\n"
            )
            for n in file_ops:
                parts.append(_tool_desc(n))

        # Agent Notebook
        nb_tools = [
            n
            for n in ("notebook_search", "notebook_add", "notebook_remove")
            if n in self._tools
        ]
        if nb_tools:
            parts.append("\n## Agent Notebook\n")
            parts.append(
                "The agent notebook (`.neoflow/agent_notebook.md`) stores reusable knowledge: "
                "working commands, solutions, patterns discovered during tasks.\n"
            )
            for n in nb_tools:
                parts.append(_tool_desc(n))

        # Task Management
        task_tools = [n for n in ("mark_task_done",) if n in self._tools]
        if task_tools:
            parts.append("\n## Task Management (multi-task workflows only)\n")
            for n in task_tools:
                parts.append(_tool_desc(n))

        # Installed pack tools (anything not in the reserved set)
        pack_tools = [
            t for name, t in self._tools.items() if name not in RESERVED_TOOL_NAMES
        ]
        if pack_tools:
            parts.append("\n## Installed Tool Packs\n")
            for t in pack_tools:
                parts.append(t.description)

        # Completion — always last
        parts.append("\n## Completion\n")
        parts.append(
            "### done\n"
            "Signal task completion with a comprehensive summary.\n"
            "```json\n"
            '{"action": "done", "summary": "Created authentication middleware in '
            "`src/middleware/auth.py` with JWT validation. Updated `src/app.py` to use the "
            'middleware. All existing tests pass."}\n'
            "```\n"
            "**Summary should include:** What was accomplished, files modified/created, "
            "verification performed."
        )

        return "\n".join(parts)

    def load_tool_pack(self, pack_dir: Path, unsafe_mode: bool = False) -> list[str]:
        """Load tools from an installed tool pack directory.

        Each Python file listed in the pack's ``manifest.json`` must export a
        ``register_tools() -> list[ToolDefinition]`` function.

        Args:
            pack_dir: Path to the extracted tool pack directory.
            unsafe_mode: When ``False``, tools with ``security_level="unsafe"``
                         are silently skipped.

        Returns:
            List of tool names that were successfully loaded.
        """
        manifest_path = pack_dir / "manifest.json"
        if not manifest_path.is_file():
            logger.warning("Tool pack missing manifest.json: %s", pack_dir)
            return []

        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)

        tag = manifest.get("metadata", {}).get("tag", pack_dir.name)
        tool_files: list[str] = manifest.get("tools", [])
        loaded_names: list[str] = []

        # Determine the common directory that holds all tool files.
        # We create a synthetic Python package rooted here so that both
        # absolute imports (from tool_definition import ...) and relative
        # imports (from .tool_definition import ...) resolve correctly.
        tool_dirs: set[Path] = {
            (pack_dir / rel).parent
            for rel in tool_files
            if (pack_dir / rel).is_file()
        }
        # Register one synthetic package per unique tool directory.
        pkg_map: dict[Path, str] = {}
        for td in tool_dirs:
            pkg_name = f"neoflow_toolpack_{tag}_{td.stem}"
            if pkg_name not in sys.modules:
                import types as _types
                pkg = _types.ModuleType(pkg_name)
                pkg.__path__ = [str(td)]  # marks it as a package
                pkg.__package__ = pkg_name
                sys.modules[pkg_name] = pkg
            pkg_map[td] = pkg_name

        for tool_rel_path in tool_files:
            tool_file = pack_dir / tool_rel_path
            if not tool_file.is_file():
                logger.warning("Tool file not found in pack '%s': %s", tag, tool_rel_path)
                continue

            tool_dir_path = tool_file.parent
            pkg_name = pkg_map.get(tool_dir_path, f"neoflow_tool_{tag}_{tool_file.stem}")
            # Load as a submodule of the synthetic package so relative imports work.
            module_name = f"{pkg_name}.{tool_file.stem}"
            tool_dir_str = str(tool_dir_path)
            try:
                spec = importlib.util.spec_from_file_location(module_name, tool_file)
                if spec is None or spec.loader is None:
                    logger.warning("Could not create module spec for: %s", tool_file)
                    continue

                mod = importlib.util.module_from_spec(spec)
                mod.__package__ = pkg_name  # required for relative imports
                sys.modules[module_name] = mod
                # Also expose as attribute on the package so intra-pack imports resolve.
                pkg_mod = sys.modules.get(pkg_name)
                if pkg_mod is not None:
                    setattr(pkg_mod, tool_file.stem, mod)
                # Add the tool directory to sys.path for absolute sibling imports.
                inserted = False
                if tool_dir_str not in sys.path:
                    sys.path.insert(0, tool_dir_str)
                    inserted = True
                try:
                    spec.loader.exec_module(mod)  # type: ignore[union-attr]
                finally:
                    if inserted and tool_dir_str in sys.path:
                        sys.path.remove(tool_dir_str)

                if not hasattr(mod, "register_tools"):
                    logger.warning(
                        "Tool file missing register_tools() in pack '%s': %s",
                        tag,
                        tool_rel_path,
                    )
                    continue

                tools: list[ToolDefinition] = mod.register_tools()
                for tool in tools:
                    if tool.security_level == "unsafe" and not unsafe_mode:
                        logger.info(
                            "Skipping unsafe tool '%s' from pack '%s' (unsafe_mode=False)",
                            tool.name,
                            tag,
                        )
                        continue
                    try:
                        self.register(tool)
                        loaded_names.append(tool.name)
                        logger.info("Loaded tool '%s' from pack '%s'", tool.name, tag)
                    except ValueError as exc:
                        logger.warning(
                            "Could not register tool '%s' from pack '%s': %s",
                            tool.name,
                            tag,
                            exc,
                        )
            except Exception as exc:
                logger.warning(
                    "Failed to import tool file '%s' from pack '%s': %s",
                    tool_rel_path,
                    tag,
                    exc,
                )

        return loaded_names
