# Agent System

Comprehensive guide to NeoFlow's autonomous agent system for complex task execution.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Features](#features)
- [Usage](#usage)
- [Planning System](#planning-system)
- [Available Tools](#available-tools)
- [Domain Knowledge](#domain-knowledge)
- [Task Management](#task-management)
- [Examples](#examples)

## Overview

The Agent System provides autonomous, multi-step task execution with planning capabilities. Unlike the chat system, the agent can perform file operations, execute code, and make complex decisions to accomplish development tasks.

### Key Characteristics

- **Autonomous**: Executes tasks with minimal human intervention
- **Planning**: Breaks complex tasks into manageable subtasks
- **Tool-Rich**: Has access to file operations, code execution, and search
- **Context-Aware**: Loads domain-specific knowledge and project configuration
- **Adaptive**: Adjusts approach based on task requirements and feedback

### Use Cases

- Code generation and modification
- Bug fixing and debugging
- Refactoring and optimization
- Documentation generation
- Test creation
- Project scaffolding
- Complex multi-file changes

## Architecture

```
┌────────────────────────────────────────────────────────┐
│                    Agent Command                        │
│                neoflow agent "task"                     │
└───────────────────────┬────────────────────────────────┘
                        │
                        ▼
┌────────────────────────────────────────────────────────┐
│              Parse Domain Mentions                      │
│              Load .neoflow/ Config                      │
└───────────────────────┬────────────────────────────────┘
                        │
                        ▼
┌────────────────────────────────────────────────────────┐
│                  Planning Phase                         │
│            (Optional, can be disabled)                  │
│  ┌──────────────────────────────────────────────┐     │
│  │  Analyze task → Generate plan → Create queue │     │
│  └──────────────────────────────────────────────┘     │
└───────────────────────┬────────────────────────────────┘
                        │
            ┌───────────┴──────────┐
            ▼                      ▼
┌────────────────────┐   ┌─────────────────────┐
│  Single Execution  │   │  Multi-Task Queue   │
│    (No plan)       │   │   (With plan)       │
└─────────┬──────────┘   └──────────┬──────────┘
          │                         │
          └────────┬────────────────┘
                   │
                   ▼
┌────────────────────────────────────────────────────────┐
│                  Execution Loop                         │
│  ┌────────────────────────────────────────────────┐   │
│  │  LLM decides action → Parse → Execute tool     │   │
│  │  Add result to history → Repeat               │   │
│  └────────────────────────────────────────────────┘   │
│                                                         │
│  Available Actions:                                     │
│  - Search (code, docs, tickets)                        │
│  - Shell Commands                                       │
│  - Ask Chat (delegate to chat system)                  │
│  - Task Management (resolve, switch)                   │
│  - Agent Notebook (search, add, remove)                │
└────────────────────────────────────────────────────────┘
                        │
                        ▼
┌────────────────────────────────────────────────────────┐
│                  Task Completion                        │
│            Report results and exit                      │
└────────────────────────────────────────────────────────┘
```

## Features

### 1. Multi-Step Planning

Breaks complex tasks into manageable subtasks:

```
Task: "Create a REST API for user management"

Plan:
1. Design database schema for users
2. Create SQLAlchemy models
3. Implement CRUD operations
4. Add API endpoints with FastAPI
5. Write unit tests
6. Update documentation
```

Each subtask is executed independently with its own context.

### 2. Tool-Based Execution

Agent uses structured tools to interact with the environment:

```json
{
  "action": "run_command",
  "command": "python -m pytest tests/"
}
```

### 3. Domain Knowledge Loading

Load specialized knowledge for specific domains:

```bash
neoflow agent "@python @fastapi Create a user registration endpoint"
```

Available domains are loaded from `~/.neoflow/agent_system_prompt/`.

### 4. Context Optimization

Automatically manages conversation history:
- Summarizes old messages when context grows large
- Preserves recent and important information
- Tracks token usage

### 5. Task Resolution Tracking

For multi-task plans, tracks resolution status:
- Completed tasks marked as resolved
- Failed tasks marked with errors
- Can switch between tasks or retry

### 6. Interactive Cancellation

User can cancel with `Ctrl+C` at any time.

## Usage

### Basic Usage

```bash
neoflow agent "Your task description"
```

### With Domain Knowledge

```bash
neoflow agent "@domain_name Task description"
```

### Without Planning

```bash
neoflow agent --no-planning "Simple task"
```

### With Custom Working Directory

```bash
neoflow agent --working-dir /path/to/project "Task"
```

### Programmatic Usage

```python
from neoflow.agent.agent import run_agent
from neoflow.config import Config
from rich.console import Console

config = Config.from_env()
console = Console()

run_agent(
    task="Create a function to validate emails",
    config=config,
    console=console
)
```

## Planning System

The planner analyzes tasks and decides execution strategy.

### When Planning Triggers

Planning is triggered for tasks that:
- Mention multiple components or files
- Use phrases like "create a system", "implement complete", "full"
- Require coordination across multiple areas
- Are complex or vague

### Planning Process

1. **Analyze Task**: Understand requirements and scope
2. **Generate Plan**: Break into logical subtasks
3. **Create Queue**: Order tasks by dependencies
4. **Generate Context**: Build system prompt with all task info

### Task Queue Structure

```python
@dataclass
class TaskQueue:
    tasks: list[str]              # Ordered subtask descriptions
    system_prompt: str            # Combined context for all tasks
    original_task: str            # Original user task
```

### Skipping Planning

Disable planning for:
- Simple, single-step tasks
- Quick file operations
- When you want direct execution

```bash
neoflow agent --no-planning "Add docstring to main()"
```

## Available Tools

### Search Operations

#### search_code
Search indexed code repositories.
```json
{
  "action": "search_code",
  "query": "authentication implementation"
}
```

#### search_documentation
Search documentation.
```json
{
  "action": "search_documentation",
  "query": "API guide"
}
```

#### search_tickets
Search support tickets.
```json
{
  "action": "search_tickets",
  "query": "bug report"
}
```

#### get_full_ticket
Retrieve complete ticket details with all comments.
```json
{
  "action": "get_full_ticket",
  "reference": "SDK-10007"
}
```

### Shell Operations

#### run_command
Execute shell commands.
```json
{
  "action": "run_command",
  "command": "pytest tests/"
}
```

### Delegation

#### ask_chat
Delegate question to chat system.
```json
{
  "action": "ask_chat",
  "question": "What are the best practices for error handling?"
}
```

### Task Management

#### resolve_task
Mark current task as complete.
```json
{
  "action": "resolve_task",
  "summary": "Created user model with validation"
}
```

#### switch_task
Switch to different task in queue.
```json
{
  "action": "switch_task",
  "task_id": 2
}
```

### Meta Operations

#### thinking
Reason without taking action.
```json
{
  "action": "thinking",
  "thoughts": "I need to first check if the file exists..."
}
```

#### done
Complete entire task.
```json
{
  "action": "done",
  "summary": "All tasks completed successfully"
}
```

## Domain Knowledge

Domain knowledge provides specialized context for specific technologies or frameworks.

### Using Domains

Reference domains with `@domain_name` in your task:

```bash
neoflow agent "@react @typescript Create a login form component"
```

### Available Domains

Domains are loaded from `~/.neoflow/agent_system_prompt/`:

- `python.md` - Python best practices
- `react.md` - React patterns
- `fastapi.md` - FastAPI conventions
- `testing.md` - Testing guidelines
- `database.md` - Database design
- (Add more as needed)

On first NeoFlow run, bundled default domain files are copied into this folder if they are missing.

### Creating Custom Domains

Create a markdown file in `~/.neoflow/agent_system_prompt/`:

```markdown
# Django Domain Knowledge

## Best Practices
- Use class-based views for complex logic
- Follow Django's model conventions
- ...

## Common Patterns
...

## Examples
...
```

Reference it: `@django`

## Task Management

For multi-task plans, agent tracks task resolution.

### Task States

- **Pending**: Not started yet
- **In Progress**: Currently executing
- **Completed**: Successfully finished
- **Failed**: Encountered error

### Task List Approach

When agent detects multiple independent tasks:

```
Task: "Fix bugs in auth.py, update docs, and add tests"

Detected 3 independent tasks:
1. Fix bugs in auth.py
2. Update documentation
3. Add tests

Each tracked separately with resolution status.
```

### Switching Tasks

Agent can switch between tasks:

```json
{
  "action": "switch_task",
  "task_id": 2,
  "reason": "Need to complete docs before tests"
}
```

## Examples

### Example 1: Simple Code Generation

**Command:**
```bash
neoflow agent "Create a function to validate email addresses"
```

**Execution:**
1. Agent decides to create a new file
2. Generates validation function with regex
3. Adds docstring and type hints
4. Creates file: `utils/validators.py`
5. Marks task as done

### Example 2: Bug Fix

**Command:**
```bash
neoflow agent "Fix the authentication bug in user_service.py where tokens expire too quickly"
```

**Execution:**
1. Read `user_service.py`
2. Search for authentication logic
3. Identify token expiration setting
4. Modify expiration time
5. Run tests to verify fix
6. Report completion

### Example 3: Complex Multi-File Task

**Command:**
```bash
neoflow agent "Create a REST API for managing blog posts with CRUD operations"
```

**Planning Phase:**
1. Analyzes requirements
2. Creates plan:
   - Design data model
   - Create database schema
   - Implement models
   - Add API endpoints
   - Write tests
   - Update docs

**Execution:**
3. For each task in queue:
   - Execute with focused context
   - Track completion
   - Move to next task

### Example 4: With Domain Knowledge

**Command:**
```bash
neoflow agent "@fastapi @sqlalchemy Create a user registration endpoint with email validation"
```

**Execution:**
1. Loads FastAPI and SQLAlchemy domain knowledge
2. Creates SQLAlchemy User model
3. Implements Pydantic schema
4. Creates FastAPI endpoint
5. Adds email validation
6. Includes proper error handling (from domain knowledge)

### Example 5: Refactoring

**Command:**
```bash
neoflow agent "Refactor payment_service.py to use async/await patterns"
```

**Execution:**
1. Read current `payment_service.py`
2. Identify synchronous operations
3. Convert functions to async
4. Update function calls
5. Add await keywords
6. Update imports
7. Run tests to verify
8. Report changes

## Configuration

Agent configuration via [config.py](../neoflow/config.py):

```python
@dataclass
class AgentConfig:
    context_token_threshold: int = 25_000
    large_message_ratio: float = 0.50
    planning_enabled: bool = True
```

### Environment Variables

```bash
# Enable/disable planning
AGENT_PLANNING_ENABLED=true

# Context management thresholds
AGENT_CONTEXT_TOKEN_THRESHOLD=25000
AGENT_LARGE_MESSAGE_RATIO=0.50
```

## Project-Local Configuration

Create `.neoflow/` directory in your project root:

```
your-project/
├── .neoflow/
│   ├── README.md          # Project context
│   ├── conventions.md     # Coding standards
│   ├── architecture.md    # System design
│   └── examples/          # Code examples
├── src/
└── ...
```

Agent automatically loads all files from `.neoflow/` directory.

## Best Practices

### 1. Clear Task Descriptions

**Good:**
```bash
neoflow agent "Add input validation to the login endpoint in api/auth.py. \
Validate email format and password length. Return 400 on invalid input."
```

**Not ideal:**
```bash
neoflow agent "fix the login thing"
```

### 2. Use Domain Knowledge

```bash
# Better
neoflow agent "@fastapi Create health check endpoint"

# Works, but less context
neoflow agent "Create health check endpoint"
```

### 3. Verify Complex Changes

For critical changes, review agent output:

```bash
neoflow agent "Refactor database connection handling" && \
git diff
```

### 4. Provide Context

```bash
# If agent needs specific information
neoflow agent "Fix bug in user_service.py. See ticket ISSUE-123 for details. \
The problem is with token refresh logic."
```

### 5. Break Down Very Complex Tasks

Instead of:
```bash
neoflow agent "Rewrite entire authentication system"
```

Consider:
```bash
neoflow agent "Step 1: Create new JWT token handler"
neoflow agent "Step 2: Update login endpoint to use new handler"
# etc.
```

## Troubleshooting

### Agent Gets Stuck

- Check if LLM is responding (verbose mode: `-v`)
- May be planning unnecessarily (use `--no-planning`)
- Context might be too large (check token usage)

### Incorrect File Modifications

- Review task description for clarity
- Check if domain knowledge might be conflicting
- Verify `.neoflow/` configuration

### Planning Too Aggressive

- Disable planning for simple tasks:
  ```bash
  neoflow agent --no-planning "Simple task"
  ```

### Out of Context

- Reduce `AGENT_CONTEXT_TOKEN_THRESHOLD`
- Clear old `.neoflow/` content
- Simplify task description

## See Also

- [CLI Reference](CLI_REFERENCE.md)
- [Chat System](CHAT_SYSTEM.md)
- [Configuration](CONFIGURATION.md)
- [Search Features](SEARCH_FEATURES.md)
