"""Domain-specific prompt loading via @mentions."""

import os
import re
from pathlib import Path

_DOMAIN_DIR = Path(__file__).resolve().parent.parent / "agent_system_prompt"


def list_domains() -> list[str]:
    """Return available domain names (filenames without .md extension)."""
    if not _DOMAIN_DIR.is_dir():
        return []
    return sorted(
        p.stem for p in _DOMAIN_DIR.iterdir() if p.suffix == ".md" and p.is_file()
    )


def load_domains(names: list[str]) -> str:
    """Read the specified domain files and concatenate their content.

    Returns the combined string to append to the base system prompt.
    Unknown domain names are silently skipped.
    """
    parts = []
    for name in names:
        path = _DOMAIN_DIR / f"{name}.md"
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
