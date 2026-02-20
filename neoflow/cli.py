import argparse
import json
import logging
import os
import sys
from datetime import datetime
import pathlib
import subprocess
import platform

from rich.console import Console
from rich.logging import RichHandler
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.table import Table

from neoflow.agent.input import multiline_prompt
from neoflow.config import Config
from neoflow.status_bar import StatusBar, status_context
from neoflow.template import load_template, run_template_form, TemplateError

console = Console()


def _setup_logging(verbose: bool = False, info : bool = False, stderr_only: bool = False):
    level = logging.DEBUG if verbose else (logging.INFO if info else logging.ERROR)
    # Use stderr console for MCP stdio mode to avoid interfering with JSON-RPC
    log_console = Console(stderr=True) if stderr_only else console
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[RichHandler(console=log_console, rich_tracebacks=True)],
    )


def _check_services(config: Config):
    """Verify that Weaviate and Ollama are reachable."""
    import weaviate
    from weaviate.config import AdditionalConfig, Timeout

    try:
        client = weaviate.connect_to_local(
            additional_config=AdditionalConfig(
                timeout=Timeout(init=5, query=5, insert=5)
            )
        )
        client.close()
    except Exception:
        console.print("[red bold]Cannot connect to Weaviate.[/red bold]")
        console.print("Make sure it's running: [cyan]docker compose up -d[/cyan]")
        sys.exit(1)

    try:
        from ollama import list as ollama_list
        ollama_list()
    except Exception:
        console.print("[red bold]Cannot connect to Ollama.[/red bold]")
        console.print("Make sure it's running: [cyan]docker compose up -d[/cyan]")
        sys.exit(1)


def cmd_search(args, config: Config):
    """Run the search/query pipeline."""
    from neoflow.chat import run_chat

    _check_services(config)

    # Interactive mode if no query provided
    if args.query:
        prompt = args.query
        project_name = args.project or ""
    else:
        console.print(Panel("NeoFlow Search", style="bold blue"))
        prompt = Prompt.ask("[bold]What are you looking for?[/bold]")
        project_name = Prompt.ask(
            "Project name or keyword to filter by", default=""
        )

    bar = StatusBar()
    bar.start()
    try:
        # Combine project_name and prompt for chat-based approach
        query_text = prompt
        if project_name:
            query_text = f"[project: {project_name}] {prompt}"
        
        answer = run_chat(
            query=query_text,
            config=config,
            console=console,
            bar=bar,
            silent=False,
        )
        answer = answer or "No answer generated"
    finally:
        bar.stop()

    console.print()
    console.print(Panel(Markdown(answer), title="Answer", border_style="green"))

    # Save option
    if args.output:
        _save_report(answer, args.output)
    elif not args.query:
        if Confirm.ask("\nSave response to a file?", default=False):
            file_name = Prompt.ask("File name (without extension)")
            _save_report(answer, file_name)


def _save_report(content: str, name: str):
    """Save an answer to the reports directory."""
    os.makedirs("reports", exist_ok=True)
    path = os.path.join("reports", f"{name}.md")
    with open(path, "w") as f:
        f.write(content)
    console.print(f"[green]Saved to {path}[/green]")


def cmd_import(args, config: Config):
    """Import tickets, documentation, or zip code into Weaviate."""
    if getattr(args, "name", None) and not getattr(args, "zip", None):
        console.print("[red bold]--name requires --zip.[/red bold]")
        sys.exit(1)

    if getattr(args, "docs", None):
        args.path = args.docs
        cmd_import_documentation(args, config)
        return

    if getattr(args, "zip", None):
        if not getattr(args, "name", None):
            console.print("[red bold]--zip requires --name.[/red bold]")
            sys.exit(1)
        args.file = args.zip
        cmd_import_zip(args, config)
        return

    if getattr(args, "tickets", False):
        from neoflow.importer.importer import import_tickets

        _check_services(config)
        import_tickets(config)
        return


def cmd_import_documentation(args, config: Config):
    """Import documentation files into Weaviate."""
    from neoflow.importer.documentation import import_documentation

    _check_services(config)

    doc_path = args.path
    if not os.path.isdir(doc_path):
        console.print(f"[red bold]Directory not found: {doc_path}[/red bold]")
        sys.exit(1)

    console.print(f"Importing documentation from [cyan]{doc_path}[/cyan]...")

    with console.status("[bold green]Importing documentation files..."):
        count = import_documentation(doc_path, config)

    console.print(f"[green]Documentation import complete: {count} chunks indexed.[/green]")


def cmd_import_zip(args, config: Config):
    """Import code from a zip file into the CodeSnippets collection."""
    from neoflow.importer.code_indexer import index_zip_file

    _check_services(config)

    zip_path = args.file
    if not os.path.isfile(zip_path):
        console.print(f"[red bold]File not found: {zip_path}[/red bold]")
        sys.exit(1)

    repo_name = args.name
    console.print(f"Importing [cyan]{zip_path}[/cyan] as [cyan]{repo_name}[/cyan]...")

    with console.status("[bold green]Extracting and indexing code from zip..."):
        index_zip_file(zip_path, repo_name, config)

    console.print(f"[green]Zip import complete: {repo_name}[/green]")


def cmd_config(args, config: Config):
    """Generate a .env template file with all configuration options."""
    output_path = args.output or ".env"
    
    # Check if file exists and prompt for confirmation
    if os.path.isfile(output_path) and not args.force:
        if not Confirm.ask(f"[yellow]{output_path} already exists. Overwrite?[/yellow]", default=False):
            console.print("[yellow]Operation cancelled.[/yellow]")
            return
    
    # Generate the template
    env_content = Config.generate_env_template()
    
    # Write to file
    with open(output_path, "w") as f:
        f.write(env_content)
    
    console.print(f"[green]✓ Generated configuration template: {output_path}[/green]")
    console.print(f"[dim]Edit the file and uncomment/modify values as needed.[/dim]")


def _print_chat_help():
    """Print available chat commands."""
    table = Table(title="Chat Commands", show_header=True, border_style="blue")
    table.add_column("Command", style="bold cyan")
    table.add_column("Description")
    table.add_row("/new", "Reset conversation and start fresh")
    table.add_row("/save <filename>", "Save the last response as a .md file")
    table.add_row("/retry", "Run the last query again")
    table.add_row("/exit", "Exit the chat")
    table.add_row("/keyword=XXXX <query>", "Set project/keyword filter, then search")
    table.add_row("/t=TEMPLATE", "Load a YAML template form and run its query")
    table.add_row("/agent", "Toggle agent mode on/off — LLM interacts with filesystem/commands")
    table.add_row("/init", "Create a .neoflow/ project config folder in the current directory")
    table.add_row("/help", "Show this help message")
    console.print(table)
    console.print()


def _save_chat_history(history: list[dict], config: Config):
    """Persist the conversation history to disk."""
    if not config.chat.save_history:
        return
    os.makedirs(config.chat.history_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(config.chat.history_dir, f"chat_{ts}.json")
    with open(path, "w") as f:
        json.dump(history, f, indent=2)
    console.print(f"[dim]Chat history saved to {path}[/dim]")


def cmd_serve(args, config: Config):
    """Start the FastAPI REST API server."""
    import uvicorn
    from neoflow.api.server import create_app

    _check_services(config)

    host = args.host or config.server.host
    port = args.port or config.server.port

    console.print(f"[green]Starting NeoFlow API server on {host}:{port}[/green]")
    console.print(f"[dim]OpenAPI docs: http://{host}:{port}/docs[/dim]")
    console.print(f"[dim]ReDoc docs: http://{host}:{port}/redoc[/dim]")
    console.print()

    app = create_app(config)
    uvicorn.run(
        app,
        host=host,
        port=port,
        reload=args.reload,
        log_level="info",
    )


def cmd_mcp_server(args, config: Config):
    """Start the MCP (Model Context Protocol) server."""
    import asyncio
    from neoflow.mcp.server import run_mcp_server

    if not config.mcp.enabled:
        console.print("[yellow]MCP server is disabled in configuration[/yellow]")
        console.print("Set MCP_ENABLED=true in your environment to enable it")
        sys.exit(1)

    transport = args.transport or config.mcp.transport

    # For stdio transport, redirect all output to stderr to avoid interfering with JSON-RPC
    if transport == "stdio":
        stderr_console = Console(stderr=True)
        stderr_console.print("[green bold]Starting NeoFlow MCP server[/green bold]")
        stderr_console.print(f"[dim]Transport: {transport}[/dim]")
        stderr_console.print(f"[dim]Available tools: ask_chat, search_code, search_documentation, search_tickets, get_full_ticket[/dim]")
        stderr_console.print("[dim]Listening on stdio (for MCP clients like VS Code, Claude Desktop)...[/dim]")
        stderr_console.print(f"[dim]Press Ctrl+C to stop[/dim]")
    else:
        console.print("[green bold]Starting NeoFlow MCP server[/green bold]")
        console.print(f"[dim]Transport: {transport}[/dim]")
        console.print(f"[dim]Available tools: ask_chat, search_code, search_documentation, search_tickets, get_full_ticket[/dim]")
        console.print(f"[dim]Listening on {config.mcp.sse_host}:{config.mcp.sse_port}...[/dim]")
        console.print(f"[dim]Press Ctrl+C to stop[/dim]")

    try:
        asyncio.run(run_mcp_server(transport=transport, config=config))
    except KeyboardInterrupt:
        stderr_console = Console(stderr=True) if transport == "stdio" else console
        stderr_console.print("\n[yellow]MCP server stopped by user[/yellow]")


def cmd_mcp_proxy(args, config: Config):
    """Start a local MCP proxy that connects to a remote NeoFlow MCP server over HTTP."""
    import asyncio
    from neoflow.mcp.proxy import run_proxy

    remote_url = args.remote_url
    auth_token = args.auth_token or config.mcp.auth_token

    console.print("[green bold]Starting NeoFlow MCP HTTP Proxy[/green bold]")
    console.print(f"[dim]Connecting to: {remote_url}[/dim]")
    console.print(f"[dim]Local protocol: stdio (for VS Code, etc.)[/dim]")
    console.print(f"[dim]Remote protocol: HTTP/SSE[/dim]")
    if auth_token:
        console.print(f"[dim]Authentication: enabled[/dim]")
    console.print(f"[dim]Press Ctrl+C to stop[/dim]")

    try:
        asyncio.run(run_proxy(remote_url=remote_url, auth_token=auth_token))
    except KeyboardInterrupt:
        console.print("\n[yellow]MCP proxy stopped by user[/yellow]")


def _resolve_server_mode(args) -> str | None:
    """Resolve requested server mode from command/flags."""
    command = getattr(args, "command", None)

    if command == "serve":
        return "rest"
    if command == "mcp-server":
        return "mcp"
    if command == "mcp-proxy":
        return "proxy"
    if command != "server":
        return None

    if getattr(args, "rest", False):
        return "rest"
    if getattr(args, "mcp", False):
        return "mcp"
    if getattr(args, "proxy", False):
        return "proxy"

    return None


def cmd_server(args, config: Config):
    """Start NeoFlow in one of the supported server modes."""
    mode = _resolve_server_mode(args)

    if mode is None:
        console.print("[red bold]Choose one mode: --rest, --mcp, or --proxy[/red bold]")
        console.print("Examples: [cyan]neoflow server --rest[/cyan], [cyan]neoflow server --mcp[/cyan], [cyan]neoflow server --proxy --remote-url http://host:9721[/cyan]")
        sys.exit(1)

    if mode == "rest":
        cmd_serve(args, config)
        return

    if mode == "mcp":
        cmd_mcp_server(args, config)
        return

    if not getattr(args, "remote_url", None):
        console.print("[red bold]--remote-url is required with --proxy[/red bold]")
        sys.exit(1)

    cmd_mcp_proxy(args, config)


def cmd_interactive(args, config: Config):
    """Run an interactive chat session with slash-command support."""
    from neoflow.chat import run_chat

    _check_services(config)

    # Session state
    history: list[dict] = []
    last_query: str | None = None
    last_keyword: str = ""
    last_answer: str | None = None
    agent_mode: bool = False

    # Define your logo/ASCII art
    logo = """
███╗   ██╗███████╗ ██████╗ ███████╗██╗      ██████╗ ██╗    ██╗
████╗  ██║██╔════╝██╔═══██╗██╔════╝██║     ██╔═══██╗██║    ██║
██╔██╗ ██║█████╗  ██║   ██║█████╗  ██║     ██║   ██║██║ █╗ ██║
██║╚██╗██║██╔══╝  ██║   ██║██╔══╝  ██║     ██║   ██║██║███╗██║
██║ ╚████║███████╗╚██████╔╝██║     ███████╗╚██████╔╝╚███╔███╔╝
╚═╝  ╚═══╝╚══════╝ ╚═════╝ ╚═╝     ╚══════╝ ╚═════╝  ╚══╝╚══╝ 
 """

    # Create header content
    header_content = f"""
    {logo}      
    """  
    from importlib import metadata 
    header_info = f"""
[bold blue]NeoFlow[/bold blue] - Version {metadata.version("neoflow")}
[bold green]Created by[/bold green]: Tadeu Arias
[bold green]Model[/bold green]: {config.llm_provider.ollama_model}
[bold green]Provider [/bold green]: {config.llm_provider.provider}
[bold green]History[/bold green]: {'on' if config.chat.save_history else 'off'}

Type [bold green]/init[/bold green] to create the local config.

Contact:
 - LinkedIn: [cyan]https://www.linkedin.com/in/traneo/[/cyan]
    """

    from rich.layout import Layout

    head_section = Layout(name="Welcome")
    head_section.split_row(
        Layout(header_content, name="Header", ratio=4),
        Layout(header_info, name="Info", ratio=2),
    )


    console.print(head_section, height=12)
    console.print("Type [bold]/help[/bold] to see available commands.")
    console.print("[dim]Multiline: Enter for newline, empty line to submit.[/dim]\n")

    while True:
        try:
            prompt_label = (
                "<magenta><b>BugSummoner &gt; </b></magenta>"
                if agent_mode
                else "<cyan><b>AI_Overlord &gt; </b></cyan>"
            )
            user_input = multiline_prompt(prompt_label, is_agent=agent_mode).strip()
        except (KeyboardInterrupt, EOFError):
            break

        if not user_input:
            continue

        # --- Slash commands ---

        lower = user_input.lower()

        if lower == "/exit":
            if history and config.chat.save_history:
                _save_chat_history(history, config)
            console.print("[bold]Goodbye![/bold]")
            break

        if lower == "/help":
            _print_chat_help()
            continue

        if lower == "/new":
            if history and config.chat.save_history:
                _save_chat_history(history, config)
            history.clear()
            last_query = None
            last_keyword = ""
            last_answer = None
            console.print("[yellow]Session reset. Starting fresh.[/yellow]\n")
            continue

        if lower.startswith("/save"):
            if last_answer is None:
                console.print("[red]Nothing to save yet.[/red]")
                continue
            parts = user_input.split(maxsplit=1)
            if len(parts) < 2 or not parts[1].strip():
                console.print("[red]Usage: /save <filename>[/red]")
                continue
            _save_report(last_answer, parts[1].strip())
            continue

        if lower == "/retry":
            if last_query is None:
                console.print("[red]No previous query to retry.[/red]")
                continue
            query = last_query
            keyword = last_keyword
            console.print(f"[dim]Retrying: {query}[/dim]")
        elif lower == "/agent":
            agent_mode = not agent_mode
            state = "on" if agent_mode else "off"
            color = "magenta" if agent_mode else "yellow"
            console.print(f"[{color}]Agent mode toggled {state}.[/{color}]")
            if agent_mode:
                console.print("[dim]Your messages will now be handled by the agent. "
                              "Type /agent again to switch back to search mode.[/dim]")
            continue
        elif lower.startswith("/keyword="):
            # Parse /keyword=VALUE <query>
            after_slash = user_input[len("/keyword="):]
            parts = after_slash.split(maxsplit=1)
            if not parts:
                console.print("[red]Usage: /keyword=PROJECT your search query[/red]")
                continue
            keyword = parts[0]
            if len(parts) < 2 or not parts[1].strip():
                console.print("[red]Usage: /keyword=PROJECT your search query[/red]")
                continue
            query = parts[1].strip()
            console.print(f"[dim]Keyword: {keyword}[/dim]")
        elif lower.startswith("/t="):
            template_name = user_input[len("/t="):].strip()
            if not template_name:
                console.print("[red]Usage: /t=template_name[/red]")
                continue
            try:
                template = load_template(template_name)
                query = run_template_form(template, console)
            except TemplateError as exc:
                console.print(f"[red]{exc}[/red]")
                continue

            if not query.strip():
                console.print("[yellow]Empty query — skipping search.[/yellow]")
                continue

            keyword = last_keyword
            console.print(f"\n[dim]Running query: {query}[/dim]")
        elif lower == "/init":
            from neoflow.init import run_init
            run_init(console)
            continue
        elif user_input.startswith("/"):
            console.print(f"[red]Unknown command: {user_input.split()[0]}[/red]")
            console.print("Type [bold]/help[/bold] for available commands.")
            continue
        elif agent_mode:
            # --- Agent mode: hand the message to the agent loop ---
            from neoflow.agent.agent import run_agent
            run_agent(user_input, config, console)
            continue
        else:
            # Plain query — use last keyword or none
            query = user_input
            keyword = last_keyword

        # --- Execute search via tool-based chat ---
        last_query = query
        last_keyword = keyword

        bar = StatusBar()
        bar.start()
        try:
            answer = run_chat(query, config, console, bar)
        finally:
            bar.stop()

        if answer:
            last_answer = answer
            history.append({
                "timestamp": datetime.now().isoformat(),
                "keyword": keyword,
                "query": query,
                "answer": answer,
            })
            console.print()
            console.print(Panel(Markdown(answer), title="Answer", border_style="green"))
            console.print()



def get_or_create_neoflow_folder(console: Console = console) -> str:
    # Get home directory in a cross-platform way
    home = pathlib.Path.home()
    neoflow_path = home / ".neoflow"

    # Create folder if it doesn't exist
    if not neoflow_path.exists():
        console.print(f"[green]Creating NeoFlow config folder at {neoflow_path}[/green]")
        neoflow_path.mkdir(parents=True, exist_ok=True)

        # On Windows, set hidden attribute
        if platform.system() == "Windows":
            subprocess.call(["attrib", "+h", str(neoflow_path)])

    return str(neoflow_path)

def main():
    parser = argparse.ArgumentParser(
        prog="neoflow",
        description="AI-powered search and analysis tool using LLM",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable debug logging"
    )
    parser.add_argument(
        "-i", "--info", action="store_true", help="Enable info logging"
    )
    parser.add_argument(
        "--provider", type=str, choices=["auto", "openai", "vllm", "ollama"],
        help="LLM provider to use (default: auto-detect)",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # search
    search_parser = subparsers.add_parser("search", help="Search tickets (single query)")
    search_parser.add_argument("-q", "--query", type=str, help="Search query")
    search_parser.add_argument("-p", "--project", type=str, help="Project name filter")
    search_parser.add_argument("-o", "--output", type=str, help="Save result to this filename")

    # import
    import_parser = subparsers.add_parser(
        "import",
        help="Import tickets, docs, or zip code into Weaviate",
    )
    mode_group = import_parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--tickets", action="store_true",
        help="Import ticket data",
    )
    mode_group.add_argument(
        "--docs", type=str, default=None,
        help="Path to documentation directory to import",
    )
    mode_group.add_argument(
        "--zip", type=str, default=None,
        help="Path to zip file to import as code",
    )
    import_parser.add_argument(
        "--name", type=str, default=None,
        help="Repository name label (required with --zip)",
    )

    # config
    config_parser = subparsers.add_parser("config", help="Generate .env configuration template")
    config_parser.add_argument(
        "-o", "--output", type=str, default=".env",
        help="Output file path (default: .env)",
    )
    config_parser.add_argument(
        "-f", "--force", action="store_true",
        help="Overwrite existing file without confirmation",
    )

    # server
    server_parser = subparsers.add_parser(
        "server",
        help="Start REST API server, MCP server, or MCP proxy",
    )
    server_mode_group = server_parser.add_mutually_exclusive_group(required=False)
    server_mode_group.add_argument(
        "--rest", action="store_true",
        help="Run REST API server",
    )
    server_mode_group.add_argument(
        "--mcp", action="store_true",
        help="Run MCP server",
    )
    server_mode_group.add_argument(
        "--proxy", action="store_true",
        help="Run local MCP HTTP proxy",
    )
    server_parser.add_argument(
        "--host", type=str, default=None,
        help="Server host (default: localhost)",
    )
    server_parser.add_argument(
        "--port", type=int, default=None,
        help="Server port (default: 9720)",
    )
    server_parser.add_argument(
        "--reload", action="store_true",
        help="Enable auto-reload for development",
    )
    server_parser.add_argument(
        "--transport", type=str, choices=["stdio", "sse"], default=None,
        help="Transport protocol (default: stdio)",
    )
    server_parser.add_argument(
        "--remote-url", type=str, default=None,
        help="Remote MCP server URL (required with --proxy)",
    )
    server_parser.add_argument(
        "--auth-token", type=str, default=None,
        help="Authentication token for remote server (optional)",
    )

    args = parser.parse_args()
    
    # For MCP server with stdio transport, we need to redirect all logging to stderr
    # to avoid interfering with JSON-RPC over stdio
    stderr_logging = False
    server_mode = _resolve_server_mode(args)
    if server_mode == "mcp":
        # Check if transport is stdio (either from args or will default to stdio)
        transport = getattr(args, "transport", None) or "stdio"  # Default is stdio
        stderr_logging = (transport == "stdio")
    
    _setup_logging(args.verbose, args.info, stderr_only=stderr_logging)

    user_config_override = get_or_create_neoflow_folder(console)

    # Load .env if available
    from dotenv import load_dotenv

    if user_config_override:
        env_path = os.path.join(user_config_override, ".env")
        if os.path.isfile(env_path):
            # Use stderr for MCP stdio mode to avoid interfering with JSON-RPC
            output_console = Console(stderr=True) if stderr_logging else console
            output_console.print(f"[green]Loading configuration from {env_path}[/green]")
            load_dotenv(env_path)
    
    load_dotenv(override=True)
    config = Config.from_env()

    # Apply CLI provider override
    if args.provider:
        config.llm_provider.provider = args.provider
    
    commands = {
        "search": cmd_search,
        "import": cmd_import,
        "config": cmd_config,
        "server": cmd_server,
        "serve": cmd_server,
        "mcp-server": cmd_server,
        "mcp-proxy": cmd_server,
    }

    if args.command in commands:
        commands[args.command](args, config)
    else:
        # No command specified - default to interactive mode
        cmd_interactive(args, config)


if __name__ == "__main__":
    main()
