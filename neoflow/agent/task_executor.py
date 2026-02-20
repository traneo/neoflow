"""Task execution tracker for agent multi-step workflows.

Integrates with the existing Planner to track task resolutions and
synthesize final answers from multiple task outcomes.
"""

import logging
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

        lines = ["Previous completed task resolutions:"]
        for res in self.current_task_list.resolutions:
            lines.append(f"- {res.task_id}: {res.task_description}")
            lines.append(f"  Result: {res.resolution}")

        return "\n".join(lines)
    
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
