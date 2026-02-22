"""Task execution tracker for agent multi-step workflows.

Integrates with the existing Planner to track task resolutions and
synthesize final answers from multiple task outcomes.
"""

import json as _json
import logging
import re as _re
from pathlib import Path
from datetime import datetime

from neoflow.agent.task_manager import TaskList, detect_task_list_needed, create_initial_task_list
from neoflow.config import Config
from neoflow.llm_provider import get_provider

logger = logging.getLogger(__name__)


class TaskExecutor:
    """Manages task execution with resolution tracking."""
    
    def __init__(self, config: Config):
        self.config = config
        self.current_task_list: TaskList | None = None
        self.task_resolutions = {}
    
    def should_use_task_list(self, prompt: str) -> bool:
        """Determine if this request needs task list management.
        
        Args:
            prompt: User's original request
        
        Returns:
            True if task list approach would be beneficial
        """
        provider = get_provider(self.config.llm_provider.provider)
        model = getattr(self.config.llm_provider, f"{provider.get_name()}_model", None)
        
        return detect_task_list_needed(prompt, provider, model, self.config)
    
    def initialize_task_list(self, prompt: str) -> TaskList | None:
        """Create and initialize a task list for this request.

        Args:
            prompt: User's original request

        Returns:
            TaskList object or None if initialization failed
        """
        provider = get_provider(self.config.llm_provider.provider)
        model = getattr(self.config.llm_provider, f"{provider.get_name()}_model", None)

        self.current_task_list = create_initial_task_list(prompt, provider, model, self.config)
        return self.current_task_list

    def initialize_from_task_queue(self, prompt: str, task_queue) -> TaskList:
        """Initialize resolution tracking directly from an existing TaskQueue.

        This avoids the redundant LLM call in ``initialize_task_list`` when the
        Planner has already produced the task list.

        Args:
            prompt: Original user request (stored for context).
            task_queue: A ``TaskQueue`` instance returned by the Planner.

        Returns:
            The newly created ``TaskList``.
        """
        task_list = TaskList(
            id=f"tasklist_{datetime.now().timestamp()}",
            original_prompt=prompt,
        )
        for i, task_desc in enumerate(task_queue.tasks):
            task_list.add_task(f"task_{i+1}", task_desc)
        self.current_task_list = task_list
        logger.info(f"Task list initialized from plan with {len(task_list.tasks)} tasks")
        return task_list
    
    def record_task_resolution(self, task_id: str, task_description: str, resolution: str, notes: str = "") -> None:
        """Record the resolution for a completed task.
        
        Args:
            task_id: Unique identifier for the task
            task_description: Human-readable task description
            resolution: The outcome/result from executing the task
            notes: Optional additional notes
        """
        if self.current_task_list:
            self.current_task_list.add_resolution(task_id, task_description, resolution, notes)
            logger.info(f"Recorded resolution for task {task_id}")

    def get_previous_resolutions_context(self) -> str:
        """Build context text containing resolutions from completed tasks.

        Returns:
            Formatted text suitable for appending to the next task prompt.
        """
        if not self.current_task_list or not self.current_task_list.resolutions:
            return "No previous task resolutions yet."

        parts: list[str] = []
        for res in self.current_task_list.resolutions:
            block = [f"**{res.task_id}: {res.task_description}**", f"Result: {res.resolution}"]
            if res.notes:
                block.append(f"Context: {res.notes}")
            parts.append("\n".join(block))

        return "\n\n".join(parts)
    
    def get_pending_tasks(self) -> list[dict]:
        """Get list of pending (incomplete) tasks.
        
        Returns:
            List of task dictionaries with id and description
        """
        if self.current_task_list:
            return self.current_task_list.pending_tasks()
        return []
    
    def all_tasks_completed(self) -> bool:
        """Check if all tasks are completed.
        
        Returns:
            True if all tasks have resolutions, False otherwise
        """
        if self.current_task_list:
            return self.current_task_list.all_completed()
        return True
    
    def get_final_synthesis(self) -> str:
        """Generate final answer by synthesizing all task resolutions.
        
        Returns:
            Synthesized final answer combining all resolutions
        """
        if not self.current_task_list or not self.current_task_list.resolutions:
            return "No task resolutions to synthesize"
        
        summary = self.current_task_list.get_summary()
        
        # Use LLM to synthesize final answer
        provider = get_provider(self.config.llm_provider.provider)
        model = getattr(self.config.llm_provider, f"{provider.get_name()}_model", None)
        
        synthesis_prompt = f"""You are synthesizing the final answer from multiple task resolutions.

{summary}

Create a comprehensive, well-organized final response that:
1. Addresses the original request
2. Incorporates findings from all tasks
3. Provides a coherent narrative
4. Highlights key results and recommendations

Generate the final answer now:"""
        
        try:
            response = provider.create_chat_completion(
                messages=[{"role": "user", "content": synthesis_prompt}],
                model=model,
            )
            
            # Extract response text
            result = ""
            if isinstance(response, dict):
                if "choices" in response and response["choices"]:
                    choice = response["choices"][0]
                    if isinstance(choice, dict) and "message" in choice:
                        result = choice["message"].get("content", "")
                    else:
                        result = choice.get("text", "")
            
            logger.info("Generated final synthesis")
            return result
        except Exception as e:
            logger.error(f"Synthesis failed: {e}")
            return self.current_task_list.get_summary()
    
    @staticmethod
    def extract_discoveries_from_messages(messages: list[dict]) -> str:
        """Extract key findings from a completed task's message history.

        Scans the message conversation for file paths referenced in the agent's
        reasoning and shell commands that executed without errors.  The result
        is a compact, human-readable summary suitable for storing in the
        resolution ``notes`` field and the cross-task discoveries scratchpad.

        Args:
            messages: The full message list for the completed task.

        Returns:
            A multi-line string of key discoveries, or an empty string if none.
        """
        _file_pat = _re.compile(
            r'[`\'"]([a-zA-Z0-9_./\-]+\.'
            r'(?:py|js|ts|jsx|tsx|json|yaml|yml|md|txt|sh|go|rs|rb|java|cpp|c|h))[`\'"]'
        )
        _action_pat = _re.compile(r'```json\s*\n(.*?)\n?\s*```', _re.DOTALL)

        found_files: set[str] = set()
        working_commands: list[str] = []
        last_command: str | None = None

        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            source_action = msg.get("_source_action", "")

            if role == "assistant":
                # Collect file paths from reasoning text
                for m in _file_pat.finditer(content):
                    path = m.group(1)
                    if "/" in path and len(path) > 4:
                        found_files.add(path)
                # Track the last proposed run_command
                for m in _action_pat.finditer(content):
                    try:
                        action = _json.loads(m.group(1))
                        if action.get("action") == "run_command":
                            last_command = action.get("command", "")
                    except (_json.JSONDecodeError, ValueError):
                        pass

            elif role == "user" and source_action == "run_command" and last_command:
                lower = content.lower()
                is_error = (
                    "error:" in lower
                    or "traceback" in lower
                    or "command not found" in lower
                    or "exit code: 1" in lower
                    or "exit code: 2" in lower
                    or "no such file" in lower
                )
                if not is_error:
                    working_commands.append(last_command)
                last_command = None

        parts: list[str] = []
        if found_files:
            file_list = sorted(found_files)[:12]
            parts.append("Key files: " + ", ".join(f"`{f}`" for f in file_list))
        if working_commands:
            # Deduplicate while preserving order
            seen: set[str] = set()
            unique_cmds = [c for c in working_commands if not (c in seen or seen.add(c))]  # type: ignore[func-returns-value]
            parts.append(
                "Working commands:\n" + "\n".join(f"  - `{c}`" for c in unique_cmds[:5])
            )

        return "\n".join(parts)

    def save_task_list(self, filepath: Path | None = None) -> Path:
        """Save the current task list to a JSON file.
        
        Args:
            filepath: Optional path to save to. Defaults to current directory.
        
        Returns:
            Path where task list was saved
        """
        if not self.current_task_list:
            raise ValueError("No active task list to save")
        
        if filepath is None:
            filepath = Path(f".neoflow/tasklist_{self.current_task_list.id}.json")
        
        filepath.parent.mkdir(parents=True, exist_ok=True)
        self.current_task_list.to_json(filepath)
        return filepath
