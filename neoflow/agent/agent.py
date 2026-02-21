import logging
import os
import re
import shlex
import subprocess

from anyio import sleep

from neoflow.llm_provider import get_provider
from neoflow.llm_error_handler import retry_llm_request
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from neoflow.agent.context_optimizer import ContextOptimizer
from neoflow.agent.domains import load_domains, parse_domain_mentions
from neoflow.agent.input import AgentCancelled, agent_prompt, run_llm_with_cancel
from neoflow.agent.loop_detector import LoopDetector
from neoflow.agent.planner import Planner
from neoflow.agent.task_executor import TaskExecutor
from neoflow.config import Config
from neoflow.init import NEOFLOW_DIR
from neoflow.prompts import AGENT_SYSTEM_PROMPT
from neoflow.search.tools import (
    parse_action,
    strip_json_blocks,
    search_code,
    search_documentation,
    search_tickets,
)
from neoflow.status_bar import StatusBar, estimate_tokens, status_context

logger = logging.getLogger(__name__)

# Tools allowed in agent mode
_AGENT_TOOLS = {
    "run_command",
    "search_code",
    "search_documentation",
    "search_tickets",
    "ask_chat",
    "ask_user",
    "notebook_search",
    "notebook_add",
    "notebook_remove",
    "done",
}


# Session-level approval toggle for run_command confirmations.
# When True, run_command actions execute without confirmation for the
# remainder of the current process/session.
_RUN_COMMANDS_AUTO_APPROVED_SESSION = False


def run_agent(task: str, config: Config, console: Console, bar: StatusBar | None = None):
    """Run the agentic loop for a given task description."""
    # Parse @domain mentions and build the system prompt
    domain_names, cleaned_task = parse_domain_mentions(task)
    domain_content = load_domains(domain_names)
    system_prompt = AGENT_SYSTEM_PROMPT
    if domain_content:
        system_prompt = system_prompt + "\n" + domain_content + "\n"

    # Load project-local .neoflow/ configuration
    system_prompt = _load_neoflow_config(system_prompt)

    # Compact init line
    domain_info = f" | {', '.join(domain_names)}" if domain_names else ""
    console.print("\n[bold green]Agent Online: Initiating Shenanigans...[/bold green]")
    console.print(f"\n[bold]Prompt[/bold]: {cleaned_task} [dim]({config.llm_provider.ollama_model}{domain_info})[/dim]")

    # Use provided bar or create a new one
    if bar is None:
        bar = StatusBar()
        bar.start()
        should_stop_bar = True
    else:
        should_stop_bar = False
    
    bar.set_message("Agent started")

    optimizer = ContextOptimizer(config, bar)
    
    # Initialize loop detector to prevent infinite loops
    loop_detector = LoopDetector(
        max_iterations=config.agent.max_iterations,
        action_window_size=config.agent.loop_action_window_size,
        repetition_threshold=config.agent.loop_repetition_threshold,
        error_threshold=config.agent.loop_error_threshold,
        pattern_length=config.agent.loop_pattern_length,
    ) if config.agent.loop_detection_enabled else None
    
    # Initialize task executor for resolution tracking
    task_executor = TaskExecutor(config)
    
    # Check if we should use task resolution tracking
    should_track_tasks = task_executor.should_use_task_list(cleaned_task)
    if should_track_tasks:
        bar.set_message("Initializing task list...")
        task_executor.initialize_task_list(cleaned_task)
        console.print("[cyan]Task list approach detected - tracking resolutions separately[/cyan]")

    # Planning phase: analyze the task and optionally generate a plan
    planner = Planner(config, bar, console)
    task_queue = planner.maybe_plan(cleaned_task, system_prompt)

    # Per-query approval state: once one run_command is approved in this query,
    # subsequent run_command actions in the same query won't ask again.
    query_confirmation_state = {"run_command_approved": False}

    try:
        if task_queue is not None:
            # Task-by-task execution: process one task at a time
            task_results = {}  # Store results for resolution tracking
            
            for i, task_desc in enumerate(task_queue.tasks):
                bar.start_task(i)
                task_id = f"task_{i+1}"
                console.print(f"\n[bold cyan]--- Task {i + 1}/{len(task_queue.tasks)}: {task_desc} ---[/bold cyan]")
                
                # console.print(task_queue.system_prompt, style="dim")
                # sleep(5)  # Brief pause for readability

                previous_resolutions_context = ""
                if should_track_tasks and task_executor.current_task_list:
                    previous_resolutions_context = task_executor.get_previous_resolutions_context()

                messages = [
                    {"role": "system", "content": task_queue.system_prompt},
                    {"role": "user", "content": f"Execute this task:\n{task_desc}\n\n{previous_resolutions_context}\n\nWorking directory: {os.getcwd()}"},
                ]
                # Reset token/message counts for fresh context
                with bar._lock:
                    bar._state.token_count = sum(
                        estimate_tokens(m["content"]) for m in messages
                    )
                    bar._state.message_count = len(messages)

                task_optimizer = ContextOptimizer(config, bar)
                # Create new loop detector for each task
                task_loop_detector = LoopDetector(
                    max_iterations=config.agent.max_iterations,
                    action_window_size=config.agent.loop_action_window_size,
                    repetition_threshold=config.agent.loop_repetition_threshold,
                    error_threshold=config.agent.loop_error_threshold,
                    pattern_length=config.agent.loop_pattern_length,
                ) if config.agent.loop_detection_enabled else None
                try:
                    while True:
                        _agent_step(
                            messages,
                            config,
                            console,
                            bar,
                            task_optimizer,
                            task_loop_detector,
                            query_confirmation_state,
                        )
                except _AgentDone as done:
                    # Extract the task result from the final "done" action
                    if done.result:
                        task_results[task_id] = done.result
                        # Record resolution if tracking is enabled
                        if should_track_tasks and task_executor.current_task_list:
                            task_executor.record_task_resolution(
                                task_id,
                                task_desc,
                                done.result,
                            )
                    bar.complete_task(i)
                    continue
            
            # All tasks done - synthesize if tracking enabled
            if should_track_tasks and task_executor.current_task_list:
                bar.set_message("Synthesizing final answer...")
                console.print("\n[cyan]Synthesizing final answer from all task resolutions...[/cyan]")
                final_answer = task_executor.get_final_synthesis()
                console.print()
                console.print(Panel(
                    Markdown(final_answer),
                    title="Final Synthesis",
                    border_style="green",
                ))
                # Save task list
                try:
                    from pathlib import Path
                    task_executor.save_task_list(Path(".neoflow/task_resolutions.json"))
                except Exception as e:
                    logger.warning(f"Could not save task list: {e}")
            
            return  # All tasks done
        else:
            # Simple task: single agent loop (no planning)
            user_msg = f"Task: {cleaned_task}\n\nWorking directory: {os.getcwd()}"
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
            ]
            bar.increment_messages(2)
            bar.add_tokens(estimate_tokens(system_prompt))
            bar.add_tokens(estimate_tokens(user_msg))

            while True:
                _agent_step(
                    messages,
                    config,
                    console,
                    bar,
                    optimizer,
                    loop_detector,
                    query_confirmation_state,
                )
    except AgentCancelled:
        console.print("\n[bold]Agent cancelled.[/bold]")
    except _AgentDone:
        pass
    finally:
        if should_stop_bar:
            bar.stop()


def _agent_step(
    messages: list[dict],
    config: Config,
    console: Console,
    status_bar: StatusBar,
    optimizer: ContextOptimizer,
    loop_detector: LoopDetector | None,
    query_confirmation_state: dict[str, bool],
) -> str | None:
    """Execute one iteration of the agent loop.

    Returns:
        The task result/summary if the agent signals completion, None otherwise.

    Raises:
        AgentCancelled: If the user cancels (Ctrl+C).
        _AgentDone: If the agent signals completion or the user exits.
    """
    status_bar.set_loading(True, "Agent is thinking...")
    # Strip internal metadata before sending to the LLM
    clean_messages = optimizer.strip_metadata(messages)
    provider = get_provider(config.llm_provider.provider)
    model = getattr(config.llm_provider, f"{provider.get_name()}_model", None)
    
    # Use retry logic with error handling
    response = retry_llm_request(
        lambda: run_llm_with_cancel(
            lambda: provider.create_chat_completion(messages=clean_messages, model=model),
            status_bar=status_bar,
        ),
        provider=provider,
        console=console,
        context="Agent thinking",
    )
    status_bar.set_loading(False)

    # Normalize response content (support different provider shapes)
    reply = ""
    try:
        if isinstance(response, dict):
            if "choices" in response and response["choices"]:
                choice = response["choices"][0]
                if isinstance(choice, dict) and "message" in choice:
                    reply = choice["message"].get("content", "")
                else:
                    reply = choice.get("text", "")
            elif "message" in response:
                # vLLM/ollama raw shape
                reply = response.get("message", {}).get("content", "")
    except Exception:
        reply = ""
    optimizer.add_message(messages, {"role": "assistant", "content": reply})
    optimizer.optimize(messages)
    status_bar.increment_messages()

    # Display the agent's reasoning (strip JSON action blocks)
    display_text = strip_json_blocks(reply).strip()
    if display_text and not display_text.startswith("{"):
        # Add reasoning to status bar
        reasoning_preview = display_text[:80] + "..." if len(display_text) > 80 else display_text
        console.print()
        console.print(Panel(Markdown(display_text), title="Agent", border_style="magenta"))

    # Parse the JSON action block from the response
    action = parse_action(reply)
    if action is None:
        # Check if the response looks like reasoning/thinking or a final answer
        if display_text and len(display_text) > 50:
            prompt_msg = (
                "I see your reasoning. What would you like to do next? "
                "Please either take an action using one of the available tools, "
                "or use the 'done' action if you have completed the task."
            )
            optimizer.add_message(messages, {"role": "user", "content": prompt_msg})
        else:
            # Response seems malformed or empty - ask for proper format
            console.print("[yellow]Could not parse response… my brain is speaking Klingon again.[/yellow]")
            logger.info("Could not parse an action from the response. Asking agent to retry...")
            logger.info(reply)
            retry_msg = (
                "I could not parse a valid JSON action from your response. "
                "Please respond with exactly one JSON action block in ```json fences."
            )
            optimizer.add_message(messages, {"role": "user", "content": retry_msg})
        
        optimizer.optimize(messages)
        status_bar.increment_messages()
        return

    act_name = action.get("action", "unknown")
    status_bar.set_last_action(act_name)

    # Handle "done" action
    if act_name == "done":
        summary = action.get("summary", "Task completed.")
        status_bar.set_message("Done")
        console.print(Panel(
            f"[bold green]{summary}[/bold green]",
            title="Agent Complete",
            border_style="green",
        ))
        raise _AgentDone(summary)  # Pass summary for task resolution tracking

    # Validate tool is allowed
    if act_name not in _AGENT_TOOLS:
        available = ", ".join(sorted(_AGENT_TOOLS - {"done"}))
        if act_name == "read_file":
            reject_msg = (
                "Action 'read_file' is not available in this agent runtime and must not be used. "
                "To inspect files, use 'run_command' with safe read-only commands (for example: "
                "sed -n '1,120p path/to/file.py', head, tail, cat, or grep). "
                f"Available actions: {available}, done."
            )
        else:
            reject_msg = (
                f"Action '{act_name}' is not available. "
                f"Available actions: {available}, done. "
                "Please choose one of the available actions."
            )
        optimizer.add_message(messages, {"role": "user", "content": reject_msg})
        optimizer.optimize(messages)
        status_bar.increment_messages()
        return

    # Display the proposed action (compact single line)
    action_display = _format_action(action)
    console.print(action_display)
    
    # Add action to status bar
    primary_key = _ACTION_PRIMARY_PARAM.get(act_name)
    action_summary = f"{act_name}"
    if primary_key and primary_key in action:
        param_val = str(action[primary_key])[:60]
        action_summary = f"{act_name}: {param_val}"

    # Ask for confirmation only for run_command.
    if act_name == "run_command":
        global _RUN_COMMANDS_AUTO_APPROVED_SESSION
        needs_confirmation = (
            not _RUN_COMMANDS_AUTO_APPROVED_SESSION
            and not query_confirmation_state.get("run_command_approved", False)
        )

        if needs_confirmation:
            user_choice = agent_prompt(
                "Allow this command?",
                choices=["y", "n", "a", "/exit"],
                default="y",
            )

            if user_choice == "/exit":
                console.print("[bold]Exiting agent mode.[/bold]")
                raise _AgentDone()

            if user_choice == "n":
                feedback = agent_prompt("Optional feedback (or Enter to skip)")
                msg = "The user declined this run_command action."
                if feedback:
                    msg += f" Feedback: {feedback}"
                msg += " Please propose a different approach or action."
                optimizer.add_message(messages, {"role": "user", "content": msg})
                optimizer.optimize(messages)
                status_bar.increment_messages()
                return

            if user_choice == "a":
                _RUN_COMMANDS_AUTO_APPROVED_SESSION = True
                query_confirmation_state["run_command_approved"] = True
                console.print("[green]Auto-approval enabled for run_command in this session.[/green]")
            else:
                query_confirmation_state["run_command_approved"] = True

    # Execute the action
    status_bar.set_loading(True, f"Executing {act_name}...")
    result = _execute_action(action, config, console, status_bar)
    status_bar.set_loading(False)

    # Add result to status bar
    result_lines = result.splitlines()
    first_line = result_lines[0] if result_lines else "(no output)"
    if len(first_line) > 60:
        first_line = first_line[:57] + "..."
    

    # Record action in loop detector (if enabled)
    if loop_detector is not None:
        was_error = "error" in result.lower() or "failed" in result.lower()
        action_params = {k: str(v) for k, v in action.items() if k != "action"}
        loop_detector.record_action(
            action_name=act_name,
            parameters=action_params,
            result=result,
            was_error=was_error,
        )
        
        # Check for loops after recording the action
        loop_result = loop_detector.check_for_loops()
        if loop_result.is_loop_detected and loop_detector.should_ask_for_intervention():
            _handle_loop_detection(loop_result, messages, console, optimizer, status_bar, loop_detector)

    # Compact result: first line + line count
    result_lines = result.splitlines()
    first_line = result_lines[0] if result_lines else "(no output)"
    if len(first_line) > 80:
        first_line = first_line[:77] + "..."
    line_info = f" ({len(result_lines)} lines)" if len(result_lines) > 1 else ""
    console.print(f"  [dim]= {first_line}{line_info}[/dim]")

    result_msg = f"Action result:\n{result}"
    optimizer.add_message(
        messages,
        {"role": "user", "content": result_msg},
        source_action=act_name,
    )
    optimizer.optimize(messages)
    status_bar.increment_messages()


_ACTION_ICONS = {
    "run_command": "💻",
    "search_code": "🔎",
    "search_documentation": "📚",
    "search_tickets": "🎫",
    "ask_chat": "💬",
    "ask_user": "🙋",
    "notebook_search": "🔖",
    "notebook_add": "📝",
    "notebook_remove": "🗑️",
    "done": "✅",
}

_ACTION_LABELS = {
    "run_command": "Run Command",
    "search_code": "Search Code",
    "search_documentation": "Search Documentation",
    "search_tickets": "Search Tickets",
    "ask_chat": "Ask Chat",
    "ask_user": "Ask User",
    "notebook_search": "Notebook Search",
    "notebook_add": "Notebook Add",
    "notebook_remove": "Notebook Remove",
    "done": "Done",
}

# Maps each action to the key of its primary parameter for compact display
_ACTION_PRIMARY_PARAM = {
    "run_command": "command",
    "search_code": "query",
    "search_documentation": "query",
    "search_tickets": "query",
    "ask_chat": "query",
    "notebook_search": "query",
    "notebook_add": "title",
    "notebook_remove": "title",
    "done": "summary",
}


def _format_action(action: dict) -> str:
    """Format an action as a compact single-line string with icon + name + primary param."""
    act = action.get("action", "unknown")
    icon = _ACTION_ICONS.get(act, "\u2699\ufe0f")
    label = _ACTION_LABELS.get(act, act)

    primary_key = _ACTION_PRIMARY_PARAM.get(act)
    primary_val = ""
    if primary_key and primary_key in action:
        primary_val = str(action[primary_key])
        if len(primary_val) > 80:
            primary_val = primary_val[:77] + "..."

    return f"{icon} [bold yellow]{label}[/bold yellow] [dim]{primary_val}[/dim]"


def _handle_loop_detection(
    loop_result,
    messages: list[dict],
    console: Console,
    optimizer: ContextOptimizer,
    status_bar: StatusBar,
    loop_detector: LoopDetector,
):
    """Handle detected loop by pausing and asking user for intervention.
    
    Args:
        loop_result: LoopDetectionResult with loop information
        messages: Current message history
        console: Rich console for output
        optimizer: Context optimizer for message management
        status_bar: Status bar for updates
        loop_detector: Loop detector instance
    """
    from neoflow.agent.loop_detector import LoopDetectionResult
    
    # Display loop warning
    severity_color = "red" if loop_result.severity == "critical" else "yellow"
    console.print()
    console.print(Panel(
        f"[{severity_color}]⚠️  Loop Detected: {loop_result.loop_type}[/{severity_color}]\n\n"
        f"{loop_result.description}\n\n"
        "[bold]Suggested Actions:[/bold]\n" +
        "\n".join(f"  • {action}" for action in loop_result.suggested_actions),
        title=f"[{severity_color}]Loop Detection Warning[/{severity_color}]",
        border_style=severity_color,
    ))
    
    # Pause status bar during user interaction
    status_bar.set_loading(False)
    
    # Ask user for intervention
    console.print("\n[bold cyan]What would you like to do?[/bold cyan]")
    console.print("  [1] Provide guidance to the agent")
    console.print("  [2] Continue anyway (ignore warning)")
    console.print("  [3] Abort agent execution")
    
    try:
        choice = agent_prompt("Your choice", choices=["1", "2", "3"], default="1")
    except AgentCancelled:
        # User pressed Ctrl+C, treat as abort
        choice = "3"
    
    if choice == "1":
        # Get user guidance
        console.print("\n[cyan]Please provide guidance or information to help the agent:[/cyan]")
        try:
            guidance = agent_prompt("Your guidance (or /exit to abort)")
        except AgentCancelled:
            raise _AgentDone()
        
        if guidance.strip() == "/exit":
            raise _AgentDone()
        
        if guidance.strip():
            # Add user guidance to message history
            intervention_msg = (
                f"The system detected that you may be stuck in a loop ({loop_result.loop_type}). "
                f"The user has provided the following guidance to help you:\n\n{guidance}\n\n"
                "Please take this feedback into account and try a different approach."
            )
            optimizer.add_message(messages, {"role": "user", "content": intervention_msg})
            optimizer.optimize(messages)
            status_bar.increment_messages()
            
            # Mark intervention in loop detector
            loop_detector.mark_intervention()
            
            console.print("[green]✓ Guidance provided to agent[/green]")
        else:
            console.print("[yellow]No guidance provided, continuing...[/yellow]")
            loop_detector.mark_intervention()
    
    elif choice == "2":
        # Continue anyway
        console.print("[yellow]Continuing execution (warning ignored)...[/yellow]")
        loop_detector.mark_intervention()
    
    elif choice == "3":
        # Abort
        console.print("[red]Aborting agent execution.[/red]")
        raise _AgentDone()


class _AgentDone(Exception):
    """Sentinel raised to break out of the agent loop cleanly."""
    def __init__(self, result: str | None = None):
        self.result = result
        super().__init__()




def _execute_action(action: dict, config: Config, console: Console | None = None, status_bar: StatusBar | None = None) -> str:
    """Execute a parsed action and return the result as a string."""
    act = action.get("action")
    try:
        if act == "run_command":
            return _run_command(action["command"])
        elif act == "search_code":
            return search_code(
                action["query"],
                config,
                limit=action.get("limit", 5),
                repository=action.get("repository"),
                language=action.get("language"),
                is_test=action.get("is_test"),
                directory=action.get("directory"),
            )
        elif act == "search_documentation":
            return search_documentation(
                action["query"],
                config,
                limit=action.get("limit", 5),
            )
        elif act == "search_tickets":
            return search_tickets(
                action["query"],
                config,
                limit=action.get("limit", 10),
            )
        elif act == "ask_chat":
            from neoflow.chat import run_chat
            answer = run_chat(action["query"], config, console, status_bar, silent=True)
            return answer or "Chat could not produce an answer."
        elif act == "ask_user":
            return _ask_user(
                question=action["question"],
                options=action.get("options"),
                allow_freeform=action.get("allow_freeform", True),
                console=console,
            )
        elif act == "notebook_search":
            return _notebook_search(action["query"])
        elif act == "notebook_add":
            return _notebook_add(action["title"], action["content"])
        elif act == "notebook_remove":
            return _notebook_remove(action["title"])
        else:
            return f"Unknown action: {act}"
    except Exception as exc:
        return f"Error: {exc}"



def _run_command(command: str) -> str:
    args = shlex.split(command)
    result = subprocess.run(
        args,
        shell=False,
        capture_output=True,
        text=True,
        timeout=30,
        cwd=os.getcwd(),
    )
    output = ""
    if result.stdout:
        output += result.stdout
    if result.stderr:
        output += ("\n" if output else "") + f"STDERR:\n{result.stderr}"
    if result.returncode != 0:
        output += f"\n(exit code: {result.returncode})"
    return output or "(no output)"


def _ask_user(
    question: str,
    options: list[str] | None = None,
    allow_freeform: bool = True,
    console: Console | None = None,
) -> str:
    """Prompt the user for clarification/help and return the captured response."""
    normalized_options = [str(opt) for opt in (options or []) if str(opt).strip()]

    if console is not None:
        body = f"[bold]{question}[/bold]"
        if normalized_options:
            option_lines = [f"[{idx}] {opt}" for idx, opt in enumerate(normalized_options, 1)]
            body += "\n\n" + "\n".join(option_lines)
            if allow_freeform:
                body += "\n[f] Enter a custom response"
        console.print()
        console.print(Panel(body, title="Agent Needs User Input", border_style="cyan"))

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






# ---------------------------------------------------------------------------
# .neoflow/ project configuration loader
# ---------------------------------------------------------------------------

def _load_neoflow_config(system_prompt: str) -> str:
    """Load .neoflow/ project files and append them to the system prompt."""
    neoflow_path = os.path.join(os.getcwd(), NEOFLOW_DIR)
    if not os.path.isdir(neoflow_path):
        return system_prompt

    sections: list[str] = []

    for filename, label in [
        ("agent_system_prompt.md", "Project System Prompt"),
        ("rules.md", "Project Rules"),
        ("guidelines.md", "Project Guidelines"),
    ]:
        filepath = os.path.join(neoflow_path, filename)
        content = _read_neoflow_file(filepath)
        if content:
            sections.append(f"# {label}\n\n{content}")

    # Load notebook as read-only reference
    notebook_path = os.path.join(neoflow_path, "agent_notebook.md")
    notebook_content = _read_neoflow_file(notebook_path)
    if notebook_content:
        sections.append(
            "# Agent Notebook (reference — use notebook actions to manage)\n\n"
            + notebook_content
        )

    if sections:
        system_prompt = system_prompt + "\n" + "\n\n".join(sections) + "\n"

    return system_prompt


def _read_neoflow_file(filepath: str) -> str:
    """Read a file and return its content, stripping HTML comments and blanks."""
    if not os.path.isfile(filepath):
        return ""
    try:
        with open(filepath) as f:
            content = f.read().strip()
    except OSError:
        return ""
    # Strip HTML comment lines (template placeholders)
    lines = [
        line for line in content.splitlines()
        if not line.strip().startswith("<!--") or not line.strip().endswith("-->")
    ]
    return "\n".join(lines).strip()


# ---------------------------------------------------------------------------
# Notebook tools
# ---------------------------------------------------------------------------

def _get_notebook_path() -> str:
    """Return the absolute path to the agent notebook file."""
    return os.path.join(os.getcwd(), NEOFLOW_DIR, "agent_notebook.md")


def _notebook_search(query: str) -> str:
    """Search the agent notebook for entries matching a keyword or regex."""
    notebook_path = _get_notebook_path()
    if not os.path.isfile(notebook_path):
        return "No agent notebook found. Run /init to create one."

    with open(notebook_path) as f:
        content = f.read()

    # Split into entries by ## headings
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
            # Fall back to plain substring match
            if query.lower() in entry.lower():
                matches.append(entry)

    if not matches:
        return f"No notebook entries matching '{query}'."
    return "\n\n".join(matches)


def _notebook_add(title: str, content: str) -> str:
    """Append a new entry to the agent notebook."""
    notebook_path = _get_notebook_path()
    if not os.path.isfile(notebook_path):
        return "No agent notebook found. Run /init to create one."

    entry = f"\n\n## {title}\n\n{content}\n"
    with open(notebook_path, "a") as f:
        f.write(entry)

    return f"Added notebook entry: {title}"


def _notebook_remove(title: str) -> str:
    """Remove a notebook entry by its exact ## heading title."""
    notebook_path = _get_notebook_path()
    if not os.path.isfile(notebook_path):
        return "No agent notebook found. Run /init to create one."

    with open(notebook_path) as f:
        content = f.read()

    # Split into entries by ## headings, keeping the preamble
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
