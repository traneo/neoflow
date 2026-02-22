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

import ollama
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from neoflow.agent.input import run_llm_with_cancel
from neoflow.config import Config
from neoflow.prompts import PLANNING_ANALYSIS_PROMPT, PLANNING_GENERATION_PROMPT
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

        # Step 2: Generate plan and task list
        self._bar.set_loading(True, "Generating plan...")
        generation = self._call_llm(
            model,
            PLANNING_GENERATION_PROMPT.format(task=task),
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
