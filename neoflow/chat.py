"""Tool-based chat loop with search-only tools.

Implements an agent-like loop restricted to search actions (search_tickets,
search_code, search_documentation) with self-validation up to a configurable
number of iterations.
"""

import logging

from neoflow.llm_provider import get_provider
from neoflow.llm_error_handler import retry_llm_request
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from neoflow.agent.context_optimizer import ContextOptimizer
from neoflow.agent.input import run_llm_with_cancel, AgentCancelled
from neoflow.config import Config
from neoflow.prompts import get_chat_system_prompt
from neoflow.search.tools import (
    parse_action,
    strip_json_blocks,
    search_code,
    search_documentation,
    search_tickets,
    get_full_ticket,
)
from neoflow.status_bar import StatusBar, estimate_tokens, status_context

logger = logging.getLogger(__name__)

# Tools allowed in chat mode
_CHAT_TOOLS = {"search_tickets", "search_code", "search_documentation", "get_full_ticket", "done"}

_TOOL_STATUS_LABELS = {
    "search_code": "Searching code...",
    "search_documentation": "Searching documentation...",
    "search_tickets": "Searching tickets...",
    "get_full_ticket": "Retrieving full ticket details...",
}


def run_chat(
    query: str,
    config: Config,
    console: Console,
    bar: StatusBar,
    silent: bool = False,
) -> str | None:
    """Run a tool-based chat loop and return the final answer (or None).

    When *silent* is True, console output is suppressed (used when the agent
    delegates a question via ``ask_chat``).  Status bar updates still occur.
    """
    max_iterations = config.chat.max_iterations
    system_prompt = get_chat_system_prompt(config, max_iterations)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": query},
    ]

    bar.set_message("Chat started")
    bar.increment_messages(2)
    bar.add_tokens(estimate_tokens(system_prompt))
    bar.add_tokens(estimate_tokens(query))

    optimizer = ContextOptimizer(config, bar)
    sources_used: list[str] = []

    try:
        for iteration in range(1, max_iterations + 1):
            step_label = f"Step {iteration}/{max_iterations}"
            bar.set_loading(True, f"{step_label}: Thinking...")

            # Send to LLM
            clean_messages = optimizer.strip_metadata(messages)
            provider = get_provider(config.llm_provider.provider)
            model = getattr(config.llm_provider, f"{provider.get_name()}_model", None)
            
            # Use retry logic with error handling
            response = retry_llm_request(
                lambda: run_llm_with_cancel(
                    lambda: provider.create_chat_completion(messages=clean_messages, model=model),
                    status_bar=bar,
                ),
                provider=provider,
                console=console,
                context=f"Chat step {iteration}/{max_iterations}",
            )
            bar.set_loading(False)

            # Normalize response content
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
                        reply = response.get("message", {}).get("content", "")
            except Exception:
                reply = ""
            optimizer.add_message(messages, {"role": "assistant", "content": reply})
            optimizer.optimize(messages)
            bar.increment_messages()

            # Display reasoning (strip JSON blocks)
            if not silent:
                display_text = strip_json_blocks(reply).strip()
                if display_text:
                    # display_text = display_text.split("```json")[0] if "```json" in display_text else display_text
                    # console.print(f"[dim]{display_text}[/dim]")
                    pass  # Suppress intermediate reasoning display in chat mode to reduce noise
                    

            # Parse action
            action = parse_action(reply)
            if action is None:
                # Check if the response looks like reasoning/thinking or a final answer
                display_text = strip_json_blocks(reply).strip()
                
                # If there's substantial reasoning content, allow it and prompt next steps
                if display_text and len(display_text) > 50:
                    if not silent:
                        pass  # Suppress intermediate reasoning display
                    
                    # Gently prompt for next action or completion
                    prompt_msg = (
                        "I see your reasoning. What would you like to do next? "
                        "Please either:\n"
                        "1. Use an available action (search_tickets, search_code, search_documentation, "
                        "get_full_ticket) to gather more information, or\n"
                        "2. Use the 'done' action with your final answer if you have sufficient information."
                        "3. Use the 'done' action if you are asking a question"
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
                bar.increment_messages()
                continue

            act_name = action.get("action", "unknown")
            bar.set_last_action(act_name)

            # Handle done
            if act_name == "done":
                summary = action.get("summary", "")
                bar.set_message("Done")
                if sources_used:
                    bar.set_message(f"Done | Sources: {', '.join(dict.fromkeys(sources_used))}")
                return summary

            # Validate tool is allowed
            if act_name not in _CHAT_TOOLS:
                reject_msg = (
                    f"Action '{act_name}' is not available in chat mode. "
                    f"Available actions: {', '.join(sorted(_CHAT_TOOLS))}. "
                    "Please use one of these or produce your final answer with 'done'."
                )
                optimizer.add_message(messages, {"role": "user", "content": reject_msg})
                optimizer.optimize(messages)
                bar.increment_messages()
                continue

            # Execute search tool
            status_label = _TOOL_STATUS_LABELS.get(act_name, f"Executing {act_name}...")
            bar.set_loading(True, f"{step_label}: {status_label}")

            result = _execute_chat_action(action, config)

            bar.set_loading(False)

            # Track sources
            source_name = act_name.replace("search_", "").title()
            sources_used.append(source_name)
            bar.set_message(f"Sources: {', '.join(dict.fromkeys(sources_used))}")

            # Compact result display
            if not silent:
                result_lines = result.splitlines()
                first_line = result_lines[0] if result_lines else "(no output)"
                if len(first_line) > 80:
                    first_line = first_line[:77] + "..."
                line_info = f" ({len(result_lines)} lines)" if len(result_lines) > 1 else ""
                console.print(f"  [dim]{act_name}: {first_line}{line_info}[/dim]")

            # Feed result back
            result_msg = f"Action result ({act_name}):\n{result}"
            optimizer.add_message(
                messages,
                {"role": "user", "content": result_msg},
                source_action=act_name,
            )
            optimizer.optimize(messages)
            bar.increment_messages()

        # Max iterations reached — force a final answer
        console.print("[yellow]Warning: Brain cells at max capacity. Please output wisdom before meltdown.[/yellow]")
        bar.set_loading(True, "Generating final answer...")
        force_msg = (
            "You have reached the maximum number of search iterations. "
            "Please produce your final answer now using the 'done' action "
            "based on what you have gathered so far."
        )
        optimizer.add_message(messages, {"role": "user", "content": force_msg})
        optimizer.optimize(messages)
        bar.increment_messages()

        clean_messages = optimizer.strip_metadata(messages)
        provider = get_provider(config.llm_provider.provider)
        model = getattr(config.llm_provider, f"{provider.get_name()}_model", None)
        
        # Use retry logic with error handling
        response = retry_llm_request(
            lambda: run_llm_with_cancel(
                lambda: provider.create_chat_completion(messages=clean_messages, model=model),
                status_bar=bar,
            ),
            provider=provider,
            console=console,
            context="Chat final answer",
        )
        bar.set_loading(False)

        # Normalize response content
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
                    reply = response.get("message", {}).get("content", "")
        except Exception:
            reply = ""
        action = parse_action(reply)
        if action and action.get("action") == "done":
            return action.get("summary", "")

        # Last resort: return whatever reasoning the LLM gave
        return strip_json_blocks(reply).strip() or reply

    except AgentCancelled:
        if not silent:
            console.print("\n[bold]Chat cancelled.[/bold]")
        return None


def _execute_chat_action(action: dict, config: Config) -> str:
    """Execute a chat-mode action (search only)."""
    act = action.get("action")
    try:
        if act == "search_tickets":
            return search_tickets(
                action["query"],
                config,
                limit=action.get("limit", 15),  # Increased default for better coverage
                include_comments=action.get("include_comments", True),  # Include comments by default
            )
        elif act == "search_code":
            return search_code(
                action["query"],
                config,
                limit=action.get("limit", 20),
                repository=action.get("repository"),
                language=action.get("language"),
                is_test=action.get("is_test"),
                directory=action.get("directory"),
            )
        elif act == "search_documentation":
            return search_documentation(
                action["query"],
                config,
                limit=action.get("limit", 20),
            )
        elif act == "get_full_ticket":
            return get_full_ticket(
                action["reference"],
                config,
            )
        else:
            return f"Unknown action: {act}"
    except Exception as exc:
        return f"Error: {exc}"
