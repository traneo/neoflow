"""Task-aware context management for the Agent.

When a user's request contains multiple tasks, the agent needs to:
1. Detect that a task list is appropriate
2. Create and track tasks
3. Store resolutions separately from main context
4. Synthesize final answer from all resolutions
"""

import json
import logging
from dataclasses import dataclass, field, asdict
from typing import Optional
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class TaskResolution:
    """Represents the outcome of a completed task."""
    task_id: str
    task_description: str
    resolution: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    notes: str = ""


@dataclass
class TaskList:
    """Manages a list of tasks and their resolutions."""
    id: str
    original_prompt: str
    tasks: list[dict] = field(default_factory=list)  # list of {id, description, status}
    resolutions: list[TaskResolution] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def add_task(self, task_id: str, description: str) -> None:
        """Add a task to the list."""
        self.tasks.append({
            "id": task_id,
            "description": description,
            "status": "pending",
        })
        logger.info(f"Task added: {task_id} - {description}")
    
    def add_resolution(self, task_id: str, task_description: str, resolution: str, notes: str = "") -> None:
        """Record resolution for a completed task."""
        res = TaskResolution(
            task_id=task_id,
            task_description=task_description,
            resolution=resolution,
            notes=notes,
        )
        self.resolutions.append(res)
        
        # Update task status
        for task in self.tasks:
            if task["id"] == task_id:
                task["status"] = "completed"
                break
        
        logger.info(f"Resolution recorded for task {task_id}")
    
    def all_completed(self) -> bool:
        """Check if all tasks are completed."""
        return all(task["status"] == "completed" for task in self.tasks)
    
    def pending_tasks(self) -> list[dict]:
        """Get list of pending tasks."""
        return [t for t in self.tasks if t["status"] == "pending"]
    
    def get_summary(self) -> str:
        """Generate a summary of all resolutions."""
        summary_parts = [f"# Summary of Resolutions\n\n**Original Request:**\n{self.original_prompt}\n"]
        
        for res in self.resolutions:
            summary_parts.append(f"## Task: {res.task_id}\n")
            summary_parts.append(f"**Description:** {res.task_description}\n\n")
            summary_parts.append(f"**Resolution:**\n{res.resolution}\n")
            if res.notes:
                summary_parts.append(f"\n**Notes:** {res.notes}\n")
            summary_parts.append("\n---\n\n")
        
        return "\n".join(summary_parts)
    
    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "original_prompt": self.original_prompt,
            "tasks": self.tasks,
            "resolutions": [asdict(r) for r in self.resolutions],
            "created_at": self.created_at,
        }
    
    def to_json(self, filepath: Path) -> None:
        """Save task list to JSON file."""
        with open(filepath, "w") as f:
            json.dump(self.to_dict(), f, indent=2)
        logger.info(f"Task list saved to {filepath}")
    
    @classmethod
    def from_json(cls, filepath: Path) -> "TaskList":
        """Load task list from JSON file."""
        with open(filepath, "r") as f:
            data = json.load(f)
        
        resolutions = [TaskResolution(**r) for r in data.get("resolutions", [])]
        task_list = cls(
            id=data["id"],
            original_prompt=data["original_prompt"],
            tasks=data.get("tasks", []),
            created_at=data.get("created_at"),
        )
        task_list.resolutions = resolutions
        return task_list


def detect_task_list_needed(prompt: str, llm_provider, model: str, config) -> bool:
    """Use LLM to detect if a task list is needed for this request.
    
    Args:
        prompt: User's original prompt
        llm_provider: LLM provider instance
        model: Model name to use
        config: Configuration object
    
    Returns:
        True if a task list would help, False otherwise
    """
    detection_prompt = f"""Analyze this user request. Should it be broken down into multiple tasks for better execution?

A task list approach is helpful when:
- The request asks to perform multiple distinct operations
- The request involves sequential steps
- You need to track progress through multiple stages
- The context window needs to be optimized for complex work

User Request:
"{prompt}"

Respond with ONLY "yes" or "no"."""

    try:
        response = llm_provider.create_chat_completion(
            messages=[{"role": "user", "content": detection_prompt}],
            model=model,
        )
        
        # Extract response text
        result = ""
        if isinstance(response, dict):
            if "choices" in response and response["choices"]:
                choice = response["choices"][0]
                if isinstance(choice, dict) and "message" in choice:
                    result = choice["message"].get("content", "").strip().lower()
                else:
                    result = choice.get("text", "").strip().lower()
        
        logger.info(f"Task list detection result: {result}")
        return "yes" in result
    except Exception as e:
        logger.warning(f"Task detection failed: {e}")
        return False


def create_initial_task_list(prompt: str, llm_provider, model: str, config) -> Optional[TaskList]:
    """Use LLM to create initial task list from prompt.
    
    Args:
        prompt: User's original prompt
        llm_provider: LLM provider instance
        model: Model name to use
        config: Configuration object
    
    Returns:
        TaskList object or None if creation failed
    """
    task_creation_prompt = f"""Break down this request into specific, actionable tasks.

User Request:
"{prompt}"

Respond with a JSON object in this format:
{{
  "tasks": [
    {{"id": "task_1", "description": "..."}},
    {{"id": "task_2", "description": "..."}}
  ]
}}

Include 2-5 tasks. Make descriptions clear and specific."""

    try:
        response = llm_provider.create_chat_completion(
            messages=[{"role": "user", "content": task_creation_prompt}],
            model=model,
        )
        
        # Extract response text
        result = ""
        if isinstance(response, dict):
            if "choices" in response and response["choices"]:
                choice = response["choices"][0]
                if isinstance(choice, dict) and "message" in choice:
                    result = choice["message"].get("content", "").strip()
                else:
                    result = choice.get("text", "").strip()
        
        # Parse JSON from response
        import re
        json_match = re.search(r"\{.*\}", result, re.DOTALL)
        if json_match:
            task_data = json.loads(json_match.group())
            task_list = TaskList(
                id=f"tasklist_{datetime.now().timestamp()}",
                original_prompt=prompt,
            )
            for task in task_data.get("tasks", []):
                task_list.add_task(task["id"], task["description"])
            
            logger.info(f"Created task list with {len(task_list.tasks)} tasks")
            return task_list
    except Exception as e:
        logger.warning(f"Task list creation failed: {e}")
        return None
