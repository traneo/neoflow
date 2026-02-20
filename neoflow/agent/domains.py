"""Domain-specific prompt loading via @mentions."""

import re
from pathlib import Path

from neoflow.init import bootstrap_user_resource_folders, get_neoflow_agent_system_prompt_dir


def _domain_dir() -> Path:
    bootstrap_user_resource_folders()
    return get_neoflow_agent_system_prompt_dir()


def list_domains() -> list[str]:
    """Return available domain names (filenames without .md extension)."""
    domain_dir = _domain_dir()
    if not domain_dir.is_dir():
        return []
    return sorted(
        p.stem for p in domain_dir.iterdir() if p.suffix == ".md" and p.is_file()
    )


def load_domains(names: list[str]) -> str:
    """Read the specified domain files and concatenate their content.

    Returns the combined string to append to the base system prompt.
    Unknown domain names are silently skipped.
    """
    domain_dir = _domain_dir()
    parts = []
    for name in names:
        path = domain_dir / f"{name}.md"
        if path.is_file():
            parts.append(path.read_text())
    return "\n\n".join(parts)


def parse_domain_mentions(text: str) -> tuple[list[str], str]:
    """Extract @domain mentions from user input.

    Returns (domain_names, cleaned_text) where cleaned_text has the
    @mentions stripped out.
    """
    available = set(list_domains())
    found: list[str] = []
    def _replace(match: re.Match) -> str:
        name = match.group(1)
        if name in available:
            found.append(name)
            return ""
        return match.group(0)

    cleaned = re.sub(r"@(\w+)", _replace, text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    # Deduplicate while preserving order
    seen = set()
    unique = []
    for name in found:
        if name not in seen:
            seen.add(name)
            unique.append(name)
    return unique, cleaned
