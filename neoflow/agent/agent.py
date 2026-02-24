import logging
import os
import re
from pathlib import Path

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
from neoflow.agent.tool_registry import ToolRegistry
from neoflow.config import Config
from neoflow.init import NEOFLOW_DIR
from neoflow.model_profiles import resolve_model_profile
from neoflow.prompts import build_agent_system_prompt
from neoflow.search.tools import (
    parse_action,
    strip_json_blocks,
)
from neoflow.status_bar import StatusBar, estimate_tokens, safe_console_print as _shared_safe_console_print

logger = logging.getLogger(__name__)


def _safe_console_print(console: Console, status_bar: StatusBar | None, *args, **kwargs) -> None:
    """Print via Rich while temporarily suspending status bar redraws."""
    _shared_safe_console_print(console, status_bar, *args, **kwargs)


# Session-level approval toggle for run_command confirmations.
# When True, run_command actions execute without confirmation for the
# remainder of the current process/session.
_RUN_COMMANDS_AUTO_APPROVED_SESSION = False


def _load_installed_tool_packs(registry: ToolRegistry, config: Config) -> None:
    """Load all installed tool packs into *registry*."""
    try:
        from neoflow.tool_pack import load_tool_registry, get_neoflow_tools_dir

        tool_reg = load_tool_registry()
        for entry in tool_reg.get("tool-packs", []):
            tag = entry.get("tag", "")
            if not tag:
                continue
            install_dir = get_neoflow_tools_dir() / tag
            if not install_dir.is_dir():
                logger.warning("Tool pack directory not found, skipping: %s", install_dir)
                continue
            loaded = registry.load_tool_pack(install_dir, unsafe_mode=config.agent.unsafe_mode)
            if loaded:
                logger.info(
                    "Loaded %d tool(s) from pack '%s': %s", len(loaded), tag, loaded
                )
    except Exception as exc:
        logger.warning("Could not load tool packs: %s", exc)


_TOOL_INVOKE_PATTERN = re.compile(r"#(\w+)(?:\s+([^#]*))?")


def parse_tool_invocations(
    text: str, registry: ToolRegistry, config: "Config"
) -> tuple[list[tuple[str, str]], str]:
    """Extract and execute explicit ``#tool_name text`` invocations from *text*.

    Returns ``(results, cleaned_text)`` where *results* is a list of
    ``(tool_name, output)`` pairs for every recognised tool invocation, and
    *cleaned_text* is *text* with those ``#tool_name …`` fragments removed.

    Tool names that are not registered in *registry* are left untouched.
    """
    results: list[tuple[str, str]] = []
    found_spans: list[tuple[int, int]] = []

    for match in _TOOL_INVOKE_PATTERN.finditer(text):
        tool_name = match.group(1)
        tool_def = registry.get(tool_name)
        if tool_def is None:
            continue  # not a known tool — leave in text
        raw_input = (match.group(2) or "").strip()
        action: dict = {"action": tool_name}
        if tool_def.primary_param:
            action[tool_def.primary_param] = raw_input
        elif raw_input:
            action["text"] = raw_input
        try:
            output = tool_def.execute(action, config)
        except Exception as exc:
            output = f"Error: {exc}"
        results.append((tool_name, output))
        found_spans.append((match.start(), match.end()))

    # Remove matched spans in reverse order to preserve indices
    cleaned = text
    for start, end in reversed(found_spans):
        cleaned = cleaned[:start] + cleaned[end:]
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    return results, cleaned


def run_agent(task: str, config: Config, console: Console, bar: StatusBar | None = None):
    """Run the agentic loop for a given task description."""
    # Build tool registry (built-ins + installed packs)
    registry = ToolRegistry()
    _load_installed_tool_packs(registry, config)

    # Parse @domain mentions and build the system prompt
    domain_names, cleaned_task = parse_domain_mentions(task)
    domain_content = load_domains(domain_names)
    system_prompt = build_agent_system_prompt(registry)

    # Wrap the system prompt with model-specific instruction tags.
    active_model = config.get_active_model_name()
    profile = resolve_model_profile(active_model)
    system_prompt = profile.wrap_system_prompt(system_prompt)
    logger.debug("Model profile '%s' applied for model '%s'", profile.name, active_model)

    # Load project-local .neoflow/ configuration
    system_prompt = _load_neoflow_config(system_prompt)

    # Domain overrides come LAST so they supersede all other prompt content.
    # Wrapped with a hard-override header so the LLM treats them as binding.
    if domain_content:
        system_prompt = (
            system_prompt
            + "\n\n## ACTIVE DOMAIN OVERRIDE (highest priority — supersedes all instructions above)\n\n"
            + domain_content
            + "\n"
        )

    # Handle explicit #tool_name invocations — execute immediately and bypass
    # the agent loop when the whole input was a tool invocation.
    tool_results, cleaned_task = parse_tool_invocations(cleaned_task, registry, config)
    if tool_results:
        for tool_name, output in tool_results:
            _safe_console_print(
                console, bar,
                Panel(output, title=f"[bold yellow]{tool_name}[/bold yellow]", border_style="yellow"),
            )
        if not cleaned_task:
            # Nothing left for the agent to do — return immediately.
            return

    # Compact init line
    domain_info = f" | {', '.join(domain_names)}" if domain_names else ""
    _safe_console_print(console, bar, "\n[bold green]Agent Online: Initiating Shenanigans...[/bold green]")
    _safe_console_print(console, bar, f"\n[bold]Prompt[/bold]: {cleaned_task} [dim]({active_model}{domain_info})[/dim]")

    # Use provided bar or create a new one
    if bar is None:
        bar = StatusBar()
        bar.start()
        should_stop_bar = True
    else:
        should_stop_bar = False
    
    bar.set_message("Agent started")

    provider = get_provider(config.llm_provider.provider)
    config.llm_provider_instance = provider

    optimizer = ContextOptimizer(config, bar, provider=provider)

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

    # Shared state: tasks marked done ahead-of-schedule by earlier task agents.
    # Maps task_id (e.g. "task_3") -> summary string.
    pre_completed: dict[str, str] = {}

    # Planning phase: analyze the task and optionally generate a plan
    planner = Planner(config, bar, console)
    task_queue = planner.maybe_plan(cleaned_task, system_prompt)

    # always initialize resolution tracking from the plan — no extra LLM call
    if task_queue is not None:
        task_executor.initialize_from_task_queue(cleaned_task, task_queue)

    # Per-query approval state: once one run_command is approved in this query,
    # subsequent run_command actions in the same query won't ask again.
    query_confirmation_state = {"run_command_approved": False}

    try:
        if task_queue is not None:
            # Task-by-task execution: process one task at a time
            task_results = {}  # Store results for resolution tracking
            shared_discoveries = ""  # cross-task discoveries scratchpad

            for i, task_desc in enumerate(task_queue.tasks):
                bar.start_task(i)
                task_id = f"task_{i+1}"

                # Skip tasks already completed ahead-of-schedule by a previous agent.
                if task_id in pre_completed:
                    pre_done_summary = pre_completed[task_id]
                    _safe_console_print(
                        console, bar,
                        f"\n[bold green]--- Task {i + 1}/{len(task_queue.tasks)}: {task_desc} "
                        f"[already completed] ---[/bold green]",
                    )
                    task_executor.record_task_resolution(
                        task_id,
                        task_desc,
                        pre_done_summary,
                        notes="Completed ahead of schedule by a previous task.",
                    )
                    bar.complete_task(i)
                    continue

                _safe_console_print(console, bar, f"\n[bold cyan]--- Task {i + 1}/{len(task_queue.tasks)}: {task_desc} ---[/bold cyan]")

                # inject plan overview and task progress so the agent
                # knows what was done, what it must do now, and what comes next.
                completed_items = "\n".join(
                    f"  ✓ [{('task_' + str(j+1))}] Task {j+1}: {t}"
                    + (" *(completed ahead of schedule)*" if f"task_{j+1}" in pre_completed else "")
                    for j, t in enumerate(task_queue.tasks[:i])
                ) if i > 0 else "  (none yet)"
                remaining_items = "\n".join(
                    f"  • [task_{j+i+2}] Task {j+i+2}: {t}" for j, t in enumerate(task_queue.tasks[i+1:])
                ) if i < len(task_queue.tasks) - 1 else "  (none)"

                plan_section = (
                    f"## Overall Plan\n{task_queue.plan}\n\n"
                    f"## Task Progress ({i+1}/{len(task_queue.tasks)})\n"
                    f"Completed:\n{completed_items}\n\n"
                    f"**→ Your Current Task (Task {i+1}):** {task_desc}\n\n"
                    f"Remaining after this:\n{remaining_items}"
                )

                # share key discoveries accumulated from previous tasks
                discoveries_section = (
                    "\n\n## Cross-Task Discoveries\n"
                    "The following was learned in previous tasks — use this context "
                    "to avoid repeating work already done:\n"
                    + shared_discoveries
                ) if shared_discoveries else ""

                # always include previous resolutions — no conditional gate
                prev_resolutions = task_executor.get_previous_resolutions_context()
                resolutions_section = (
                    f"\n\n## Previous Task Resolutions\n{prev_resolutions}"
                ) if prev_resolutions != "No previous task resolutions yet." else ""

                user_content = (
                    f"{plan_section}"
                    f"{discoveries_section}"
                    f"{resolutions_section}\n\n"
                    f"Working directory: {os.getcwd()}"
                )

                messages = [
                    {"role": "system", "content": task_queue.system_prompt},
                    {"role": "user", "content": user_content},
                ]
                # Reset token/message counts for fresh context
                with bar._lock:
                    bar._state.token_count = sum(
                        estimate_tokens(m["content"]) for m in messages
                    )
                    bar._state.message_count = len(messages)

                task_optimizer = ContextOptimizer(config, bar, provider=provider)
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
                            pre_completed=pre_completed,
                            provider=provider,
                            registry=registry,
                        )
                except _AgentDone as done:
                    if done.result:
                        task_results[task_id] = done.result
                        # extract key findings from full message history
                        discoveries = TaskExecutor.extract_discoveries_from_messages(messages)
                        task_executor.record_task_resolution(
                            task_id,
                            task_desc,
                            done.result,
                            notes=discoveries,
                        )
                        # append discoveries to cross-task scratchpad
                        if discoveries:
                            shared_discoveries += (
                                f"\n### Task {i+1}: {task_desc[:60]}\n{discoveries}\n"
                            )
                    bar.complete_task(i)
                    continue

            # All tasks done - synthesize resolutions
            if task_executor.current_task_list:
                bar.set_message("Synthesizing final answer...")
                _safe_console_print(console, bar, "\n[cyan]Synthesizing final answer from all task resolutions...[/cyan]")
                final_answer = task_executor.get_final_synthesis()
                _safe_console_print(console, bar)
                _safe_console_print(console, bar, Panel(
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
                    provider=provider,
                    registry=registry,
                )
    except AgentCancelled:
        _safe_console_print(console, bar, "\n[bold]Agent cancelled.[/bold]")
    except _AgentDone:
        pass
    finally:
        if should_stop_bar:
            bar.stop()
        provider.close()


def _agent_step(
    messages: list[dict],
    config: Config,
    console: Console,
    status_bar: StatusBar,
    optimizer: ContextOptimizer,
    loop_detector: LoopDetector | None,
    query_confirmation_state: dict[str, bool],
    pre_completed: dict[str, str] | None = None,
    provider=None,
    registry: ToolRegistry | None = None,
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
    if provider is None:
        provider = get_provider(config.llm_provider.provider)
    model = getattr(config.llm_provider, f"{provider.get_name()}_model", None)
    step_profile = resolve_model_profile(model or "")

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
    # Strip model-specific control tokens (e.g. Harmony channel headers for gpt-oss)
    reply = step_profile.clean_reply(reply)
    optimizer.add_message(messages, {"role": "assistant", "content": reply})
    optimizer.optimize(messages)
    status_bar.increment_messages()

    # Display the agent's reasoning (strip JSON action blocks)
    display_text = strip_json_blocks(reply).strip()
    if display_text and not display_text.startswith("{"):
        # Add reasoning to status bar
        reasoning_preview = display_text[:80] + "..." if len(display_text) > 80 else display_text
        _safe_console_print(console, status_bar)
        _safe_console_print(console, status_bar, Panel(Markdown(display_text), title="Agent", border_style="magenta"))

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
            _safe_console_print(console, status_bar, "[yellow]Could not parse response… my brain is speaking Klingon again.[/yellow]")
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

    # Ensure we have a registry (fallback to default built-ins)
    if registry is None:
        registry = ToolRegistry()

    # Handle "done" action
    if act_name == "done":
        summary = action.get("summary", "Task completed.")
        status_bar.set_message("Done")
        _safe_console_print(console, status_bar, Panel(
            f"[bold green]{summary}[/bold green]",
            title="Agent Complete",
            border_style="green",
        ))
        raise _AgentDone(summary)  # Pass summary for task resolution tracking

    # Validate tool is registered
    tool_def = registry.get(act_name)
    if tool_def is None:
        available = ", ".join(sorted(registry.all_names()))
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
    action_display = _format_action(action, registry)
    _safe_console_print(console, status_bar, action_display)

    # Security gate — handle approval and unsafe tool confirmation
    if tool_def.security_level == "approval":
        global _RUN_COMMANDS_AUTO_APPROVED_SESSION
        needs_confirmation = (
            not config.agent.unsafe_mode
            and not _RUN_COMMANDS_AUTO_APPROVED_SESSION
            and not query_confirmation_state.get("run_command_approved", False)
        )

        if needs_confirmation:
            user_choice = agent_prompt(
                "Allow this action?",
                choices=["y", "n", "a", "/exit"],
                default="y",
                console=console,
                status_bar=status_bar,
                modal_title="Action Approval Required",
                modal_body=(
                    f"[bold]Allow {tool_def.label}?[/bold]\n\n"
                    "y) Yes, run once\n"
                    "n) No, reject this action\n"
                    "a) Always allow approval-level actions for this session\n"
                    "/exit) Exit agent mode"
                ),
                modal_style="yellow",
            )

            if user_choice == "/exit":
                _safe_console_print(console, status_bar, "[bold]Exiting agent mode.[/bold]")
                raise _AgentDone()

            if user_choice == "n":
                feedback = agent_prompt("Optional feedback (or Enter to skip)")
                msg = f"The user declined the {act_name} action."
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
                _safe_console_print(
                    console, status_bar,
                    "[green]Auto-approval enabled for this session.[/green]",
                )
            else:
                query_confirmation_state["run_command_approved"] = True

    elif tool_def.security_level == "unsafe":
        # Unsafe tools always require explicit per-action approval
        user_choice = agent_prompt(
            "Allow this UNSAFE action?",
            choices=["y", "n", "/exit"],
            default="n",
            console=console,
            status_bar=status_bar,
            modal_title="UNSAFE Action Approval Required",
            modal_body=(
                f"[bold red]This is an UNSAFE action: {tool_def.label}[/bold red]\n\n"
                "y) Yes, run this unsafe action\n"
                "n) No, reject this action\n"
                "/exit) Exit agent mode"
            ),
            modal_style="red",
        )

        if user_choice == "/exit":
            _safe_console_print(console, status_bar, "[bold]Exiting agent mode.[/bold]")
            raise _AgentDone()

        if user_choice == "n":
            feedback = agent_prompt("Optional feedback (or Enter to skip)")
            msg = f"The user declined the unsafe {act_name} action."
            if feedback:
                msg += f" Feedback: {feedback}"
            msg += " Please propose a different approach."
            optimizer.add_message(messages, {"role": "user", "content": msg})
            optimizer.optimize(messages)
            status_bar.increment_messages()
            return

    # Execute the action via registry
    status_bar.set_loading(True, f"Executing {act_name}...")
    try:
        result = tool_def.execute(
            action,
            config,
            console=console,
            status_bar=status_bar,
            pre_completed=pre_completed,
        )
    except Exception as exc:
        result = f"Error: {exc}"
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
    _safe_console_print(console, status_bar, f"  [dim]= {first_line}{line_info}[/dim]")

    result_msg = f"Action result:\n{result}"
    if act_name == "run_command" and result.startswith("COMMAND FAILED"):
        result_msg += (
            "\n\n⚠️  The command above FAILED. "
            "Do NOT assume the operation succeeded or move on as if it did. "
            "Read the error output carefully, then either correct the command or try a different approach."
        )
    optimizer.add_message(
        messages,
        {"role": "user", "content": result_msg},
        source_action=act_name,
    )
    optimizer.optimize(messages)
    status_bar.increment_messages()


def _format_action(action: dict, registry: ToolRegistry | None = None) -> str:
    """Format an action as a compact single-line string with icon + name + primary param."""
    act = action.get("action", "unknown")

    tool_def = registry.get(act) if registry else None
    icon = tool_def.icon if tool_def else "⚙️"
    label = tool_def.label if tool_def else act
    primary_key = tool_def.primary_param if tool_def else None

    # Special-case the "done" action which isn't a ToolDefinition
    if act == "done":
        icon = "✅"
        label = "Done"
        primary_key = "summary"

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
    _safe_console_print(console, status_bar)
    _safe_console_print(console, status_bar, Panel(
        f"[{severity_color}]⚠️  Loop Detected: {loop_result.loop_type}[/{severity_color}]\n\n"
        f"{loop_result.description}\n\n"
        "[bold]Suggested Actions:[/bold]\n" +
        "\n".join(f"  • {action}" for action in loop_result.suggested_actions),
        title=f"[{severity_color}]Loop Detection Warning[/{severity_color}]",
        border_style=severity_color,
    ))
    
    # Pause status bar during user interaction
    status_bar.set_loading(False)
    
    try:
        choice = agent_prompt(
            "Select an option",
            choices=["1", "2", "3"],
            default="1",
            console=console,
            status_bar=status_bar,
            modal_title="Loop Intervention Required",
            modal_body=(
                "[bold cyan]What would you like to do?[/bold cyan]\n\n"
                "1) Provide guidance to the agent\n"
                "2) Continue anyway (ignore warning)\n"
                "3) Abort agent execution"
            ),
            modal_style=severity_color,
        )
    except AgentCancelled:
        # User pressed Ctrl+C, treat as abort
        choice = "3"
    
    if choice == "1":
        # Get user guidance
        _safe_console_print(console, status_bar, "\n[cyan]Please provide guidance or information to help the agent:[/cyan]")
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
            
            _safe_console_print(console, status_bar, "[green]✓ Guidance provided to agent[/green]")
        else:
            _safe_console_print(console, status_bar, "[yellow]No guidance provided, continuing...[/yellow]")
            loop_detector.mark_intervention()
    
    elif choice == "2":
        # Continue anyway
        _safe_console_print(console, status_bar, "[yellow]Continuing execution (warning ignored)...[/yellow]")
        loop_detector.mark_intervention()
    
    elif choice == "3":
        # Abort
        _safe_console_print(console, status_bar, "[red]Aborting agent execution.[/red]")
        raise _AgentDone()


class _AgentDone(Exception):
    """Sentinel raised to break out of the agent loop cleanly."""
    def __init__(self, result: str | None = None):
        self.result = result
        super().__init__()










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


