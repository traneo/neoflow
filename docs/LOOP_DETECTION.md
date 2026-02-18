# Loop Detection System

## Overview

The loop detection system monitors agent execution to identify when the agent gets stuck in repetitive patterns or infinite loops. When a loop is detected, the system pauses execution and asks for user intervention to resolve the issue.

## How It Works

The loop detector tracks agent actions and identifies four types of problematic patterns:

### 1. **Iteration Limit**
- **What**: Total number of agent iterations exceeds the configured maximum
- **Default**: 50 iterations
- **When triggered**: Agent has been running longer than expected
- **Severity**: Critical

### 2. **Error Cycle**
- **What**: Agent encounters multiple consecutive errors
- **Default**: 3 consecutive errors
- **When triggered**: Same error keeps occurring repeatedly
- **Severity**: Critical

### 3. **Action Repetition**
- **What**: Same action with similar parameters is repeated multiple times
- **Default**: 3 repetitions
- **When triggered**: Agent keeps trying the same thing expecting different results
- **Severity**: Warning → Critical (increases with repetitions)

### 4. **Pattern Detection**
- **What**: A sequence of actions repeats in a cycle
- **Default**: Patterns of 3+ actions
- **When triggered**: Agent is cycling through the same sequence of steps
- **Severity**: Warning → Critical (increases with repetitions)

## User Intervention

When a loop is detected, the system will:

1. **Display a warning** showing:
   - Type of loop detected
   - Description of the problem
   - Suggested actions to resolve it

2. **Pause execution** and present three options:
   - **Provide guidance**: Give the agent specific instructions or information to help it proceed
   - **Continue anyway**: Ignore the warning and let the agent continue (not recommended for critical loops)
   - **Abort**: Stop agent execution

3. **If guidance is provided**: The system adds your input to the agent's context and resets loop counters

## Configuration

Loop detection can be configured through environment variables or the config file:

### Enable/Disable

```bash
# Disable loop detection entirely
export AGENT_LOOP_DETECTION_ENABLED=false
```

### Thresholds

```bash
# Maximum iterations before triggering (default: 50)
export AGENT_MAX_ITERATIONS=100

# Size of action history window (default: 10)
export AGENT_LOOP_ACTION_WINDOW_SIZE=15

# Number of repetitions to trigger warning (default: 3)
export AGENT_LOOP_REPETITION_THRESHOLD=4

# Number of consecutive errors to trigger warning (default: 3)
export AGENT_LOOP_ERROR_THRESHOLD=5

# Length of patterns to detect (default: 3)
export AGENT_LOOP_PATTERN_LENGTH=4
```

### Configuration in Code

```python
from neoflow.config import Config

config = Config.from_env()

# Adjust loop detection settings
config.agent.loop_detection_enabled = True
config.agent.max_iterations = 75
config.agent.loop_repetition_threshold = 4
```

## Examples

### Example 1: Command Failure Loop

**Scenario**: Agent keeps trying to run a command that doesn't work

```
⚠️  Loop Detected: action_repetition

Agent is repeating the same action: 'run_command' with similar 
parameters (4 times)

Suggested Actions:
  • Explain why 'run_command' keeps failing or producing inadequate results
  • Suggest alternative actions or approaches
  • Provide the information the agent is looking for directly
  • Clarify the task requirements

What would you like to do?
  [1] Provide guidance to the agent
  [2] Continue anyway (ignore warning)
  [3] Abort agent execution

Your choice [1]: 1

Your guidance: The command requires sudo permissions. Run it with 
sudo or provide the necessary credentials.
```

### Example 2: Error Cycle

**Scenario**: Agent encounters permission errors repeatedly

```
⚠️  Loop Detected: error_cycle

Agent encountered 3 consecutive errors

Suggested Actions:
  • Review the error messages and provide guidance
  • Check if required files or resources exist
  • Verify the environment is properly configured
  • Simplify the task or change the approach
```

### Example 3: Pattern Loop

**Scenario**: Agent is cycling through the same sequence of actions

```
⚠️  Loop Detected: pattern

Agent is repeating a pattern of actions 3 times: 
[search_code → ask_chat → run_command]

Suggested Actions:
  • Identify why this sequence isn't making progress
  • Provide missing information or context
  • Break the cycle by suggesting a different approach
  • Check if the agent has all required resources
```

## Best Practices

### When Providing Guidance

1. **Be specific**: Tell the agent exactly what's wrong or what information it needs
2. **Provide context**: Explain why the current approach isn't working
3. **Suggest alternatives**: Recommend a different approach or action
4. **Give information directly**: If the agent is looking for specific data, provide it

### Adjusting Thresholds

- **Increase thresholds** if you're working on complex tasks that naturally require many iterations
- **Decrease thresholds** if you want earlier detection and more frequent interventions
- **Disable detection** for debugging or when you know the agent needs to explore extensively

### Monitoring

The loop detector runs silently until a threshold is reached. You can monitor agent progress through:
- The status bar showing iteration count
- Action history in the console
- Error patterns in output

## Technical Details

### Implementation

- **Class**: `LoopDetector` in `neoflow/agent/loop_detector.py`
- **Integration**: Called after each action execution in `_agent_step()`
- **State**: Maintains sliding window of recent actions with full history
- **Reset**: Automatically resets after user intervention

### Action Recording

Each action is recorded with:
- Action name (e.g., `search_code`, `run_command`)
- Parameters (e.g., `{'query': 'authentication'}`)
- Result summary (truncated to 200 chars)
- Error status (boolean)

### Detection Algorithms

1. **Repetition**: Compares last N actions for identical name + similar parameters
2. **Pattern**: Searches for repeating sequences of action names
3. **Error tracking**: Maintains consecutive error counter, resets on success
4. **Iteration counting**: Simple counter from agent loop start

### Intervention Spacing

To avoid annoying frequent prompts, the system waits at least 5 iterations between interventions, even if multiple loop conditions are triggered.

## Troubleshooting

### False Positives

If you're seeing too many false positive loop detections:

1. Increase the repetition or pattern thresholds
2. Increase the max iterations limit
3. Provide more specific initial instructions to the agent
4. Consider if the task is too complex and needs breaking down

### Missed Detections

If loops aren't being detected when they should be:

1. Decrease the thresholds
2. Check if loop detection is enabled
3. Verify the action window size is large enough to capture patterns
4. Review the agent logs for the actual action sequence

### Performance Impact

Loop detection has minimal performance impact:
- O(n) complexity for most checks where n = window size (typically 10)
- Memory footprint: ~1KB per action record
- CPU: Negligible (runs after each action, not in hot path)

## Future Enhancements

Potential improvements planned:

- [ ] Semantic similarity detection (not just exact parameter matches)
- [ ] Learning from user interventions to prevent similar loops
- [ ] Automatic retry strategies for common loop types
- [ ] Integration with planning system for better loop prevention
- [ ] Exportable loop reports for analysis
- [ ] Configurable severity levels and auto-responses

## See Also

- [AGENT_SYSTEM.md](./AGENT_SYSTEM.md) - Overview of the agent system
- [CONFIGURATION.md](./CONFIGURATION.md) - Complete configuration reference
- [CLI_REFERENCE.md](./CLI_REFERENCE.md) - Command-line interface guide
