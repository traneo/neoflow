"""Loop detection system for agent execution to prevent infinite loops."""

import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Literal

logger = logging.getLogger(__name__)


@dataclass
class ActionRecord:
    """Record of an executed action."""
    action_name: str
    parameters: dict[str, str]
    result_summary: str
    was_error: bool


@dataclass
class LoopDetectionResult:
    """Result from loop detection check."""
    is_loop_detected: bool
    loop_type: Literal["action_repetition", "error_cycle", "iteration_limit", "pattern"] | None = None
    description: str = ""
    severity: Literal["warning", "critical"] = "warning"
    suggested_actions: list[str] = field(default_factory=list)


class LoopDetector:
    """Detects when the agent is stuck in a repetitive loop."""
    
    def __init__(
        self,
        max_iterations: int = 50,
        action_window_size: int = 10,
        repetition_threshold: int = 3,
        error_threshold: int = 3,
        pattern_length: int = 3,
    ):
        """Initialize loop detector.
        
        Args:
            max_iterations: Maximum allowed iterations before triggering
            action_window_size: Number of recent actions to keep in memory
            repetition_threshold: How many times same action triggers warning
            error_threshold: How many consecutive errors trigger warning
            pattern_length: Length of action sequences to check for patterns
        """
        self.max_iterations = max_iterations
        self.action_window_size = action_window_size
        self.repetition_threshold = repetition_threshold
        self.error_threshold = error_threshold
        self.pattern_length = pattern_length
        
        # State
        self.iteration_count = 0
        self.action_history: deque[ActionRecord] = deque(maxlen=action_window_size)
        self.consecutive_errors = 0
        self.last_user_intervention = 0  # Track when we last asked for help
        
    def reset(self):
        """Reset detector state (e.g., when starting a new task)."""
        self.iteration_count = 0
        self.action_history.clear()
        self.consecutive_errors = 0
        self.last_user_intervention = 0
        
    def record_action(
        self, 
        action_name: str,
        parameters: dict | None = None,
        result: str = "",
        was_error: bool = False,
    ):
        """Record an executed action.
        
        Args:
            action_name: Name of the action (e.g., 'search_code', 'run_command')
            parameters: Action parameters (e.g., {'query': 'authentication'})
            result: Result summary (truncated for storage)
            was_error: Whether the action resulted in an error
        """
        self.iteration_count += 1
        
        # Track consecutive errors
        if was_error:
            self.consecutive_errors += 1
        else:
            self.consecutive_errors = 0
        
        # Store action with truncated result
        result_summary = result[:200] if result else ""
        record = ActionRecord(
            action_name=action_name,
            parameters=parameters or {},
            result_summary=result_summary,
            was_error=was_error,
        )
        self.action_history.append(record)
        
        logger.debug(
            f"Recorded action #{self.iteration_count}: {action_name} "
            f"(error={was_error}, consecutive_errors={self.consecutive_errors})"
        )
    
    def check_for_loops(self) -> LoopDetectionResult:
        """Check if agent appears stuck in a loop.
        
        Returns:
            LoopDetectionResult with detection status and recommendations
        """
        # Check 1: Iteration limit
        if self.iteration_count >= self.max_iterations:
            return LoopDetectionResult(
                is_loop_detected=True,
                loop_type="iteration_limit",
                severity="critical",
                description=f"Agent has executed {self.iteration_count} iterations (limit: {self.max_iterations})",
                suggested_actions=[
                    "Provide more specific instructions",
                    "Break the task into smaller subtasks",
                    "Check if the task requirements are clear",
                    "Abort and try a different approach",
                ],
            )
        
        # Check 2: Consecutive errors
        if self.consecutive_errors >= self.error_threshold:
            return LoopDetectionResult(
                is_loop_detected=True,
                loop_type="error_cycle",
                severity="critical",
                description=f"Agent encountered {self.consecutive_errors} consecutive errors",
                suggested_actions=[
                    "Review the error messages and provide guidance",
                    "Check if required files or resources exist",
                    "Verify the environment is properly configured",
                    "Simplify the task or change the approach",
                ],
            )
        
        # Check 3: Action repetition (same action/params multiple times)
        if len(self.action_history) >= self.repetition_threshold:
            repetition = self._detect_action_repetition()
            if repetition:
                return repetition
        
        # Check 4: Repeating patterns (sequences of actions)
        if len(self.action_history) >= self.pattern_length * 2:
            pattern = self._detect_pattern()
            if pattern:
                return pattern
        
        # No loops detected
        return LoopDetectionResult(is_loop_detected=False)
    
    def _detect_action_repetition(self) -> LoopDetectionResult | None:
        """Detect if same action is being repeated multiple times."""
        if len(self.action_history) < self.repetition_threshold:
            return None
        
        # Check last N actions
        recent_actions = list(self.action_history)[-self.repetition_threshold:]
        
        # Check if all actions are the same
        first = recent_actions[0]
        if all(
            a.action_name == first.action_name and
            self._params_similar(a.parameters, first.parameters)
            for a in recent_actions
        ):
            # Count total occurrences in history
            total_count = sum(
                1 for a in self.action_history
                if a.action_name == first.action_name and
                self._params_similar(a.parameters, first.parameters)
            )
            
            return LoopDetectionResult(
                is_loop_detected=True,
                loop_type="action_repetition",
                severity="warning" if total_count < self.repetition_threshold + 2 else "critical",
                description=(
                    f"Agent is repeating the same action: '{first.action_name}' "
                    f"with similar parameters ({total_count} times)"
                ),
                suggested_actions=[
                    f"Explain why '{first.action_name}' keeps failing or producing inadequate results",
                    "Suggest alternative actions or approaches",
                    "Provide the information the agent is looking for directly",
                    "Clarify the task requirements",
                ],
            )
        
        return None
    
    def _detect_pattern(self) -> LoopDetectionResult | None:
        """Detect repeating patterns in action sequences."""
        if len(self.action_history) < self.pattern_length * 2:
            return None
        
        recent = list(self.action_history)[-self.pattern_length * 3:]
        
        # Check for repeating patterns of different lengths
        for pattern_len in range(self.pattern_length, len(recent) // 2 + 1):
            pattern = [a.action_name for a in recent[:pattern_len]]
            
            # Check if this pattern repeats
            repetitions = 0
            for i in range(pattern_len, len(recent), pattern_len):
                chunk = [a.action_name for a in recent[i:i+pattern_len]]
                if chunk == pattern:
                    repetitions += 1
                else:
                    break
            
            if repetitions >= 2:  # Pattern repeats at least twice
                pattern_str = " → ".join(pattern)
                return LoopDetectionResult(
                    is_loop_detected=True,
                    loop_type="pattern",
                    severity="warning" if repetitions == 2 else "critical",
                    description=(
                        f"Agent is repeating a pattern of actions {repetitions + 1} times: "
                        f"[{pattern_str}]"
                    ),
                    suggested_actions=[
                        "Identify why this sequence isn't making progress",
                        "Provide missing information or context",
                        "Break the cycle by suggesting a different approach",
                        "Check if the agent has all required resources",
                    ],
                )
        
        return None
    
    def _params_similar(self, params1: dict, params2: dict, threshold: float = 0.8) -> bool:
        """Check if two parameter dicts are similar enough to be considered the same.
        
        Args:
            params1: First parameter dict
            params2: Second parameter dict
            threshold: Similarity threshold (0-1)
        
        Returns:
            True if parameters are similar enough
        """
        # Extract main parameters (ignore minor differences)
        key_params1 = {k: v for k, v in params1.items() if k in ('path', 'query', 'command', 'pattern')}
        key_params2 = {k: v for k, v in params2.items() if k in ('path', 'query', 'command', 'pattern')}
        
        # If key parameters are identical, consider similar
        if key_params1 == key_params2:
            return True
        
        # Check if main parameter values are similar (for minor variations)
        if len(key_params1) == 0 or len(key_params2) == 0:
            return False
        
        # Simple string similarity check for path/command variations
        for key in key_params1:
            if key in key_params2:
                val1 = str(key_params1[key]).lower()
                val2 = str(key_params2[key]).lower()
                if val1 == val2:
                    return True
        
        return False
    
    def should_ask_for_intervention(self) -> bool:
        """Determine if enough iterations have passed since last intervention.
        
        Prevents asking user too frequently.
        
        Returns:
            True if we should ask for user help
        """
        # Ask for intervention if we haven't done so in the last 5 iterations
        iterations_since_last = self.iteration_count - self.last_user_intervention
        return iterations_since_last >= 5
    
    def mark_intervention(self):
        """Mark that user intervention occurred."""
        self.last_user_intervention = self.iteration_count
        # Reset error counter after intervention
        self.consecutive_errors = 0
