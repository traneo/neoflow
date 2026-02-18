"""Error handling for LLM provider requests with retry/abort logic.

Handles request failures, timeouts, and connectivity issues by prompting
the user for action and checking provider availability.
"""

import logging
from typing import Callable, Optional, Any

from rich.console import Console
from rich.panel import Panel

from neoflow.agent.input import agent_prompt, AgentCancelled

logger = logging.getLogger(__name__)


class LLMRequestError(Exception):
    """Base exception for LLM request errors."""
    pass


class LLMTimeoutError(LLMRequestError):
    """Raised when an LLM request times out."""
    pass


class LLMConnectionError(LLMRequestError):
    """Raised when connectivity to LLM provider fails."""
    pass


def check_provider_connectivity(provider) -> tuple[bool, str]:
    """Check if an LLM provider is currently reachable.
    
    Args:
        provider: An LLMProvider instance to check
        
    Returns:
        A tuple of (is_available, status_message)
    """
    try:
        is_available = provider.is_available()
        if is_available:
            return True, f"{provider.get_name()} provider is reachable"
        else:
            return False, f"{provider.get_name()} provider is not reachable"
    except Exception as e:
        logger.debug(f"Error checking provider connectivity: {e}")
        return False, f"Unable to check {provider.get_name()} connectivity: {e}"


def handle_llm_request_error(
    error: Exception,
    provider,
    console: Console,
    context: str = "LLM request",
) -> str:
    """Handle an LLM request error with user interaction.
    
    Checks provider connectivity and prompts the user to retry or abort.
    
    Args:
        error: The exception that occurred
        provider: The LLM provider that failed
        console: Rich console for output
        context: Description of the operation (e.g., "Agent thinking", "Chat response")
        
    Returns:
        User's choice: "retry" or "abort"
        
    Raises:
        AgentCancelled: If the user chooses to abort or cancels the prompt
    """
    console.print()
    
    # Determine error type
    error_type = "Request failed"
    if "timeout" in str(error).lower() or isinstance(error, TimeoutError):
        error_type = "Request timeout"
    elif "connection" in str(error).lower() or isinstance(error, ConnectionError):
        error_type = "Connection error"
    
    # Check provider connectivity
    is_connected, connectivity_msg = check_provider_connectivity(provider)
    
    # Build error message
    error_parts = [
        f"[bold red]❌ {error_type}[/bold red]",
        f"[yellow]Context:[/yellow] {context}",
        f"[yellow]Provider:[/yellow] {provider.get_name()}",
        f"[yellow]Error:[/yellow] {str(error)}",
        "",
        f"[cyan]Connectivity check:[/cyan] {connectivity_msg}",
    ]
    
    # Add recommendation based on connectivity
    if is_connected:
        error_parts.append("")
        error_parts.append("[green]✓ Provider is still reachable[/green]")
        error_parts.append("[bold]Recommendation:[/bold] Retry the request")
    else:
        error_parts.append("")
        error_parts.append("[red]✗ Provider is not currently reachable[/red]")
        error_parts.append("[bold]Recommendation:[/bold] Abort and check provider status")
    
    error_message = "\n".join(error_parts)
    
    # Display error panel
    console.print(Panel(
        error_message,
        title="LLM Request Error",
        border_style="red",
        expand=False,
    ))
    
    # Prompt user for action
    console.print()
    try:
        choice = agent_prompt(
            "How would you like to proceed?",
            choices=["retry", "abort"],
            default="retry" if is_connected else "abort"
        )
        
        if choice == "abort":
            raise AgentCancelled()
        
        return choice
    except AgentCancelled:
        console.print("\n[bold yellow]Operation aborted by user.[/bold yellow]")
        raise


def retry_llm_request(
    request_fn: Callable[[], Any],
    provider,
    console: Console,
    context: str = "LLM request",
    max_retries: int = 3,
) -> Any:
    """Execute an LLM request with error handling and retry logic.
    
    Args:
        request_fn: The function that makes the LLM request
        provider: The LLM provider being used
        console: Rich console for output
        context: Description of the operation
        max_retries: Maximum number of retry attempts
        
    Returns:
        The result of the request_fn
        
    Raises:
        AgentCancelled: If the user aborts
        LLMRequestError: If all retries are exhausted
    """
    retry_count = 0
    
    while retry_count <= max_retries:
        try:
            return request_fn()
        except Exception as exc:
            # Log the error
            logger.error(f"LLM request failed (attempt {retry_count + 1}): {exc}")
            
            # If we've exhausted retries, raise the error
            if retry_count >= max_retries:
                console.print(f"\n[bold red]Maximum retry attempts ({max_retries}) reached.[/bold red]")
                raise LLMRequestError(f"Failed after {max_retries} retries: {exc}")
            
            # Handle the error and get user's choice
            choice = handle_llm_request_error(exc, provider, console, context)
            
            if choice == "retry":
                retry_count += 1
                retry_msg = f"Retrying request (attempt {retry_count + 1}/{max_retries + 1})..."
                console.print(f"\n[cyan]{retry_msg}[/cyan]")
            else:
                # This shouldn't happen as handle_llm_request_error raises AgentCancelled for abort
                raise AgentCancelled()
    
    # This shouldn't be reached, but just in case
    raise LLMRequestError("Unexpected error in retry logic")
