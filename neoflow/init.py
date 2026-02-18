"""Scaffold a .neoflow/ project configuration directory."""

import os

from rich.console import Console

NEOFLOW_DIR = ".neoflow"

_TEMPLATES: dict[str, str] = {
    "agent_system_prompt.md": (
        "# Agent System Prompt\n"
        "\n"
        "<!-- Add custom instructions that will be appended to the agent's system prompt. -->\n"
        "<!-- Example: domain-specific rules, preferred coding style, project conventions. -->\n"
    ),
    "rules.md": (
        "# Rules\n"
        "\n"
        "<!-- Define strict rules the agent must follow for this project. -->\n"
        "<!-- Example: \"Always use type hints\", \"Never modify files under /vendor\". -->\n"
    ),
    "guidelines.md": (
        "# Guidelines\n"
        "\n"
        "<!-- Provide softer recommendations and best practices for the agent. -->\n"
        "<!-- Example: preferred libraries, naming conventions, architectural patterns. -->\n"
    ),
    "agent_notebook.md": (
        "# Agent Notebook\n"
        "\n"
        "<!-- This file is managed by the agent. It records useful notes, working commands, -->\n"
        "<!-- and solutions discovered during tasks so they can be reused in future sessions. -->\n"
        "<!-- Format: each entry starts with a ## heading followed by its content. -->\n"
    ),
    "README.md": (
        "# .neoflow — Project Configuration\n"
        "\n"
        "This directory contains project-specific configuration for NeoFlow's agent mode.\n"
        "All files are automatically loaded when the agent starts in this working directory.\n"
        "\n"
        "## Files\n"
        "\n"
        "| File | Purpose | Loaded into |\n"
        "|------|---------|-------------|\n"
        "| `agent_system_prompt.md` | Custom instructions appended to the agent's system prompt | Agent system prompt |\n"
        "| `rules.md` | Strict rules the agent must follow (e.g. coding standards, forbidden actions) | Agent system prompt |\n"
        "| `guidelines.md` | Softer recommendations and best practices | Agent system prompt |\n"
        "| `agent_notebook.md` | Agent-managed notebook for recording useful findings and commands | Agent system prompt (read-only reference) |\n"
        "| `README.md` | This documentation file | Not loaded |\n"
        "\n"
        "## How It Works\n"
        "\n"
        "When you enter agent mode, NeoFlow checks for a `.neoflow/` directory in the\n"
        "current working directory. If found, the contents of `agent_system_prompt.md`,\n"
        "`rules.md`, and `guidelines.md` are appended to the agent's system prompt,\n"
        "giving the agent project-specific context.\n"
        "\n"
        "### Agent Notebook\n"
        "\n"
        "The `agent_notebook.md` file is special — it is both loaded as a reference for\n"
        "the agent **and** managed by the agent using built-in notebook tools:\n"
        "\n"
        "- **notebook_search** — Search the notebook for a keyword or pattern.\n"
        "- **notebook_add** — Record a new entry (e.g. a working command, a fix, a pattern).\n"
        "- **notebook_remove** — Remove an outdated or invalid entry.\n"
        "\n"
        "This allows the agent to learn from previous sessions. For example, if a build\n"
        "command required several attempts to get right, the agent records the working\n"
        "command so it can reuse it next time.\n"
        "\n"
        "## Tips\n"
        "\n"
        "- Keep rules and guidelines concise — they consume agent context.\n"
        "- Use `rules.md` for hard constraints and `guidelines.md` for preferences.\n"
        "- You can edit `agent_notebook.md` manually to seed it with project knowledge.\n"
        "- Add `.neoflow/agent_notebook.md` to `.gitignore` if you don't want to share\n"
        "  agent notes across team members.\n"
    ),
}


def run_init(console: Console) -> None:
    """Create the .neoflow/ directory and template files in the cwd."""
    neoflow_path = os.path.join(os.getcwd(), NEOFLOW_DIR)
    created_dir = False

    if not os.path.isdir(neoflow_path):
        os.makedirs(neoflow_path)
        created_dir = True
        console.print(f"[green]Created {NEOFLOW_DIR}/[/green]")
    else:
        console.print(f"[dim]{NEOFLOW_DIR}/ already exists[/dim]")

    for filename, content in _TEMPLATES.items():
        filepath = os.path.join(neoflow_path, filename)
        if os.path.exists(filepath):
            console.print(f"  [dim]Skipped {filename} (already exists)[/dim]")
        else:
            with open(filepath, "w") as f:
                f.write(content)
            console.print(f"  [green]Created {filename}[/green]")

    if created_dir:
        console.print(f"\n[bold green]Initialized {NEOFLOW_DIR}/ successfully.[/bold green]")
        console.print(f"[dim]See {NEOFLOW_DIR}/README.md for details on each file.[/dim]")
    else:
        console.print(f"\n[bold]Initialization complete.[/bold] Missing files were added.")
