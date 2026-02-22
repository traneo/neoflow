"""Planning phase for the agent loop.

Analyzes the user's task, optionally reads referenced files, and generates
a structured Plan + Task list.  Returns a TaskQueue so the agent can execute
one task at a time with a fresh context for each.
"""

import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import ollama
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from neoflow.agent.input import AgentCancelled, agent_prompt, run_llm_with_cancel
from neoflow.config import Config
from neoflow.prompts import PLANNING_ANALYSIS_PROMPT, PLANNING_CONTEXT_PROMPT, PLANNING_GENERATION_PROMPT
from neoflow.status_bar import StatusBar, estimate_tokens, safe_console_print

logger = logging.getLogger(__name__)


@dataclass
class TaskQueue:
    """Holds the generated plan and an ordered list of individual tasks."""

    plan: str                    # The generated plan text (for display)
    tasks: list[str]             # Ordered list of task descriptions
    system_prompt: str           # Preserved for context rebuilds


class Planner:
    """Orchestrates a planning phase before the main agent loop."""

    def __init__(self, config: Config, status_bar: StatusBar, console: Console) -> None:
        self._config = config
        self._bar = status_bar
        self._console = console

    def maybe_plan(self, task: str, system_prompt: str) -> TaskQueue | None:
        """Analyze the task and optionally generate a plan.

        Returns a TaskQueue if planning was performed, or None if the task is
        simple enough to skip planning.
        """
        if not self._config.agent.planning_enabled:
            return None

        provider = self._config.llm_provider.provider
        if provider == "openai":
            model = self._config.llm_provider.openai_model
        elif provider == "ollama":
            model = self._config.llm_provider.ollama_model
        elif provider == "vllm":
            model = self._config.llm_provider.vllm_model
        else:
            model = self._config.llm_provider.ollama_model  # fallback

        # Step 1: Analyze whether planning is needed
        self._bar.set_loading(True, "Analyzing task...")
        analysis = self._call_llm(
            model,
            PLANNING_ANALYSIS_PROMPT.format(task=task),
        )
        self._bar.set_loading(False)

        parsed = self._parse_json(analysis)
        if parsed is None or not parsed.get("needs_planning", False):
            logger.info("Planner: skipping planning for this task")
            return None

        # Step 1.5: Gather file context before generating the plan so the
        # planner has real code to reason about instead of planning blind.
        context_section = self._gather_file_context(task, model)

        # Step 2: Generate plan and task list
        self._bar.set_loading(True, "Generating plan...")
        generation = self._call_llm(
            model,
            self._build_generation_prompt(task, context_section),
        )
        self._bar.set_loading(False)

        gen_parsed = self._parse_json(generation)
        if gen_parsed is None:
            logger.warning("Planner: failed to parse generation response")
            return None

        plan = gen_parsed.get("plan", "")
        tasks_raw = gen_parsed.get("tasks", "")

        if not plan and not tasks_raw:
            return None

        # Parse individual tasks from the tasks markdown
        task_list = self._parse_task_list(tasks_raw)
        if not task_list:
            # Fall back: treat the whole tasks block as a single task
            if tasks_raw:
                task_list = [tasks_raw.strip()]
            else:
                task_list = [task]

        # Step 4: Compact display — single blue panel with plan + tasks
        display_parts: list[str] = []
        if plan:
            # Truncate plan to first 3 lines for compact display
            plan_lines = plan.strip().splitlines()
            if len(plan_lines) > 3:
                display_parts.append("\n".join(plan_lines[:3]) + f"\n... (+{len(plan_lines) - 3} lines)")
            else:
                display_parts.append(plan.strip())

        if task_list:
            display_parts.append("")
            display_parts.append("**Tasks:**")
            for i, t in enumerate(task_list, 1):
                display_parts.append(f"{i}. {t}")

        safe_console_print(self._console, self._bar)
        safe_console_print(self._console, self._bar, Panel(
            Markdown("\n".join(display_parts)),
            title="Plan",
            border_style="blue",
        ))

        # Step 5: Populate the status bar task panel
        bar_tasks = [(t, "pending") for t in task_list]
        self._bar.set_tasks(bar_tasks)

        return TaskQueue(
            plan=plan,
            tasks=task_list,
            system_prompt=system_prompt,
        )

    @staticmethod
    def _parse_task_list(tasks_text: str) -> list[str]:
        """Parse a markdown task/checklist into individual task strings."""
        if not tasks_text:
            return []
        tasks: list[str] = []
        for line in tasks_text.strip().splitlines():
            line = line.strip()
            # Match "- [ ] ...", "- ...", "1. ...", "* ..."
            m = re.match(r"^(?:[-*]|\d+\.)\s*(?:\[.\]\s*)?(.*)", line)
            if m:
                desc = m.group(1).strip()
                if desc:
                    tasks.append(desc)
        return tasks

    def _gather_file_context(self, task: str, model: str) -> str:
        """Ask the LLM which files are needed to plan this task, read them, and
        return a formatted context block ready for injection into the planning prompt.

        The total lines across all files are treated as a shared pool (configured
        via ``AGENT_PLANNING_CONTEXT_MAX_LINES``).  When the files exceed the pool,
        the user is warned and asked to confirm before proceeding with proportionally
        truncated content.  Returning an empty string falls through to blind planning.
        """
        self._bar.set_loading(True, "Gathering file context for planning...")
        raw = self._call_llm(model, PLANNING_CONTEXT_PROMPT.format(task=task))
        self._bar.set_loading(False)

        parsed = self._parse_json(raw)
        if not parsed or not parsed.get("needs_file_context", False):
            logger.info("Planner: no file context needed before planning")
            return ""

        requested = parsed.get("files") or []
        if not requested:
            return ""

        max_files = self._config.agent.planning_context_max_files
        line_pool = self._config.agent.planning_context_max_lines
        cwd = Path(os.getcwd()).resolve()

        # ------------------------------------------------------------------
        # Phase 1 — read all requested files (up to max_files)
        # Each entry: (display_path, resolved_path | None, lines | None)
        # None resolved_path  → path was unsafe
        # None lines          → file not found / unreadable
        # ------------------------------------------------------------------
        loaded: list[tuple[str, Path | None, list[str] | None]] = []

        for raw_path in requested[:max_files]:
            try:
                resolved = (cwd / raw_path).resolve()
                resolved.relative_to(cwd)
            except (ValueError, Exception):
                logger.warning("Planner: skipping unsafe path '%s'", raw_path)
                loaded.append((raw_path, None, None))
                continue

            if not resolved.is_file():
                logger.info("Planner: context file not found: %s", raw_path)
                loaded.append((raw_path, resolved, None))
                continue

            try:
                lines = resolved.read_text(errors="replace").splitlines(keepends=True)
                loaded.append((raw_path, resolved, lines))
                logger.info("Planner: read '%s' (%d lines)", raw_path, len(lines))
            except OSError as exc:
                logger.warning("Planner: could not read '%s': %s", raw_path, exc)
                loaded.append((raw_path, resolved, None))

        # Files that were actually read successfully
        readable = [(p, r, ls) for p, r, ls in loaded if ls is not None]
        total_lines = sum(len(ls) for _, _, ls in readable)

        # ------------------------------------------------------------------
        # Phase 2 — check pool, warn user if truncation is needed
        # ------------------------------------------------------------------
        allocations: dict[str, int] = {}   # path → lines to include
        truncated_paths: set[str] = set()

        if total_lines > line_pool:
            # Build a summary table for the warning
            table_rows = "\n".join(
                f"  • {p}: {len(ls):,} lines"
                for p, _, ls in readable
            )
            self._bar.set_loading(False)
            safe_console_print(self._console, self._bar)
            safe_console_print(self._console, self._bar, Panel(
                f"[yellow]Total context ({total_lines:,} lines) exceeds the configured pool "
                f"({line_pool:,} lines, set via AGENT_PLANNING_CONTEXT_MAX_LINES).[/yellow]\n\n"
                f"Files requested:\n{table_rows}\n\n"
                "Content will be [bold]proportionally truncated[/bold] across all files if you proceed.\n"
                "To avoid truncation, increase [bold]AGENT_PLANNING_CONTEXT_MAX_LINES[/bold] in your .env.",
                title="[yellow]Pre-Planning Context Too Large[/yellow]",
                border_style="yellow",
            ))

            try:
                choice = agent_prompt(
                    "Proceed with truncated context?",
                    choices=["y", "n"],
                    default="y",
                    console=self._console,
                    status_bar=self._bar,
                    modal_title="Context Truncation Required",
                    modal_body=(
                        "[bold]The gathered file context exceeds the line pool.[/bold]\n\n"
                        "y) Proceed — truncate proportionally and continue planning\n"
                        "n) Abort — skip file context and plan without it"
                    ),
                    modal_style="yellow",
                )
            except AgentCancelled:
                choice = "n"

            if choice == "n":
                safe_console_print(
                    self._console, self._bar,
                    "[yellow]Context gathering aborted — planning without file context.[/yellow]",
                )
                return ""

            # Distribute the pool proportionally (each file gets at least 1 line)
            for p, _, ls in readable:
                share = max(1, int(len(ls) / total_lines * line_pool))
                allocations[p] = share
                if share < len(ls):
                    truncated_paths.add(p)
        else:
            # Fits entirely — include every line of every readable file
            for p, _, ls in readable:
                allocations[p] = len(ls)

        # ------------------------------------------------------------------
        # Phase 3 — build the context block
        # ------------------------------------------------------------------
        parts: list[str] = []

        for display_path, resolved, lines in loaded:
            if lines is None:
                label = "_(unsafe path — skipped)_" if resolved is None else "_(file not found — skipped)_"
                parts.append(f"### `{display_path}`\n{label}")
                continue

            keep = allocations[display_path]
            chunk = lines[:keep]
            content = "".join(chunk)
            ext = resolved.suffix.lstrip(".") or "text"

            if display_path in truncated_paths:
                cut = len(lines) - keep
                note = f"\n[... {cut:,} lines truncated — increase AGENT_PLANNING_CONTEXT_MAX_LINES to include full file]"
            else:
                note = ""

            parts.append(f"### `{display_path}`\n```{ext}\n{content}{note}\n```")

        if not parts:
            return ""

        reason = parsed.get("reason", "")
        header = (
            f"\n# Pre-Planning File Context\n\n_{reason}_\n\n"
            if reason
            else "\n# Pre-Planning File Context\n\n"
        )
        return header + "\n\n".join(parts) + "\n"

    @staticmethod
    def _build_generation_prompt(task: str, context_section: str) -> str:
        """Build the plan-generation prompt, injecting file context before the
        instructions block so the planner reasons over real code."""
        base = PLANNING_GENERATION_PROMPT.format(task=task)
        if not context_section:
            return base
        # Inject the context block between the Task section and the Instructions
        # section so it reads naturally and is close to the task description.
        return base.replace("\n# Instructions", context_section + "\n# Instructions", 1)

    def _call_llm(self, model: str, prompt: str) -> str:
        """Call the LLM with a single user message and return the response text."""
        provider = self._config.llm_provider.provider
        messages = [{"role": "user", "content": prompt}]
        llm = getattr(self._config, "llm_provider_instance", None)
        if provider == "openai":
            response = run_llm_with_cancel(
                lambda: llm.create_chat_completion(
                    messages=messages,
                    model=model
                ),
                status_bar=self._bar,
            )
            return response["choices"][0]["message"]["content"]
        elif provider == "vllm":
            response = run_llm_with_cancel(
                lambda: llm.create_chat_completion(
                    messages=messages,
                    model=model
                ),
                status_bar=self._bar,
            )
            return response["choices"][0]["message"]["content"]
        else:  # ollama or fallback
            response = run_llm_with_cancel(
                lambda: llm.create_chat_completion(
                    messages=messages,
                    model=model
                ),
                status_bar=self._bar,
            )
            return response["choices"][0]["message"]["content"]

    def _parse_json(self, text: str) -> dict | None:
        """Extract a JSON object from fenced ```json blocks or raw JSON."""
        fence_match = re.search(r"```json\s*\n(.*?)\n\s*```", text, re.DOTALL)
        if fence_match:
            try:
                return json.loads(fence_match.group(1))
            except json.JSONDecodeError:
                pass

        # Fall back to finding any JSON object
        for match in re.finditer(r"\{[^{}]*\}", text):
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                continue

        return None
