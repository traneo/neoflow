"""Tool pack lifecycle management for NeoFlow.

Tool packs are ``.ntp`` zip archives that bundle one or more Python tool
files and a ``manifest.json``.  They extend the agent with new actions at
runtime without modifying core files.

Lifecycle:
    build       → ``build_tool_pack(source_dir)``     → produces a ``.ntp`` file
    install     → ``install_tool_pack(file, config)``  → extracts to ~/.neoflow/tools/{tag}/
    uninstall   → ``uninstall_tool_pack(tag)``         → removes files + registry entry
    list        → ``list_tool_packs()``                → reads the registry

Manifest format (``manifest.json`` inside the ``.ntp`` zip)::

    {
      "metadata": {
        "name": "My Tools",
        "tag": "my-tools",
        "version": "1.0.0",
        "description": "...",
        "author": "...",
        "license": "MIT"
      },
      "tools": ["tools/git_tool.py", "tools/http_tool.py"],
      "dependencies": ["requests>=2.28", "httpx"]
    }

``dependencies`` is optional.  When present, each entry is a pip requirement
specifier.  They are installed with ``sys.executable -m pip install`` into the
active Python environment (no system-level overrides).  Dependencies are
recorded in the registry but are **not** uninstalled when the pack is removed.

Each Python file must export ``register_tools() -> list[ToolDefinition]``.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path

from neoflow.init import get_neoflow_home_path

TOOL_MANIFEST_FILENAME = "manifest.json"
TOOL_REGISTRY_FILENAME = "tool-pack.json"
TOOL_PACK_DIR = "tools"

_SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")


def _install_tool_dependencies(deps: list[str]) -> list[str]:
    """Install pip packages into the active Python environment.

    Uses ``sys.executable -m pip install`` so packages land in whichever
    environment neoflow itself is running in (typically its own venv).
    No ``--break-system-packages``, ``--user``, or other override flags are
    used — pip's default behaviour is intentionally preserved.

    Args:
        deps: Pip requirement specifiers, e.g. ``["requests>=2.28", "httpx"]``.

    Returns:
        List of specifiers that failed to install (empty means all succeeded).
    """
    failed: list[str] = []
    for dep in deps:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", dep],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            failed.append(dep)
    return failed


def _slugify_tool_tag(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", name.strip().lower())
    cleaned = re.sub(r"-+", "-", cleaned).strip("-")
    if not cleaned:
        raise ValueError("Tool name must include at least one letter or digit")
    return cleaned


def _to_class_name(tag: str) -> str:
    parts = [part for part in re.split(r"[^a-zA-Z0-9]+", tag) if part]
    return "".join(part[:1].upper() + part[1:] for part in parts) or "CustomTool"


def _trim_tool_suffix(name: str) -> str:
    if name.endswith("-tool"):
        return name[:-5]
    if name.endswith("_tool"):
        return name[:-5]
    return name


# ---------------------------------------------------------------------------
# Validation result
# ---------------------------------------------------------------------------


@dataclass
class ToolManifestValidationResult:
    manifest: dict
    errors: list[str]


# ---------------------------------------------------------------------------
# Registry helpers
# ---------------------------------------------------------------------------


def get_tool_registry_path() -> Path:
    """Return the path to ``~/.neoflow/tool-pack.json``."""
    return get_neoflow_home_path() / TOOL_REGISTRY_FILENAME


def get_neoflow_tools_dir() -> Path:
    """Return ``~/.neoflow/tools/`` — where installed packs are extracted."""
    return get_neoflow_home_path() / TOOL_PACK_DIR


def _default_tool_registry() -> dict:
    return {"metadata": {}, "tool-packs": []}


def _normalize_tool_registry(raw: dict | None) -> dict:
    registry = _default_tool_registry()
    if isinstance(raw, dict):
        packs = raw.get("tool-packs")
        if isinstance(packs, list):
            registry["tool-packs"] = packs
    return registry


def load_tool_registry() -> dict:
    """Load the tool-pack registry from disk, returning a default if absent."""
    registry_path = get_tool_registry_path()
    if not registry_path.exists():
        return _default_tool_registry()
    with open(registry_path, encoding="utf-8") as f:
        return _normalize_tool_registry(json.load(f))


def save_tool_registry(registry: dict) -> None:
    """Persist the tool-pack registry to disk."""
    normalized = _normalize_tool_registry(registry)
    registry_path = get_tool_registry_path()
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    with open(registry_path, "w", encoding="utf-8") as f:
        json.dump(normalized, f, indent=2)


# ---------------------------------------------------------------------------
# Manifest validation
# ---------------------------------------------------------------------------


def _is_non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_tool_manifest(manifest: dict, package_root: Path) -> list[str]:
    """Validate a tool pack manifest dict.

    Returns a list of error strings; empty list means the manifest is valid.
    """
    errors: list[str] = []

    metadata_block = manifest.get("metadata")
    if not isinstance(metadata_block, dict):
        errors.append("missing section: metadata")
        return errors

    for field_name in ("name", "tag", "version", "description", "author", "license"):
        if not _is_non_empty_string(metadata_block.get(field_name)):
            errors.append(f"metadata.{field_name} is required")

    version_value = metadata_block.get("version")
    if _is_non_empty_string(version_value) and not _SEMVER_PATTERN.match(
        version_value.strip()
    ):
        errors.append("metadata.version must follow semver format X.Y.Z")

    tools_list = manifest.get("tools")
    if tools_list is None:
        errors.append("missing field: tools (must be a list of Python file paths)")
    elif not isinstance(tools_list, list):
        errors.append("tools must be a list of file paths")
    else:
        for tool_path in tools_list:
            if not _is_non_empty_string(tool_path):
                errors.append("tools entries must be non-empty strings")
                continue
            full = (package_root / tool_path).resolve()
            if not full.is_file():
                errors.append(f"tool file not found: {tool_path}")

    deps = manifest.get("dependencies")
    if deps is not None:
        if not isinstance(deps, list):
            errors.append("dependencies must be a list of pip requirement specifiers")
        else:
            for dep in deps:
                if not _is_non_empty_string(dep):
                    errors.append("dependencies entries must be non-empty strings")

    return errors


def validate_tool_manifest_from_path(package_root: Path) -> ToolManifestValidationResult:
    """Load and validate the manifest inside *package_root*."""
    manifest_path = package_root / TOOL_MANIFEST_FILENAME
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)
    errors = validate_tool_manifest(manifest, package_root)
    return ToolManifestValidationResult(manifest=manifest, errors=errors)


# ---------------------------------------------------------------------------
# Filename helper
# ---------------------------------------------------------------------------


def tool_pack_filename(manifest: dict) -> str:
    """Return the canonical filename for the given manifest (e.g. ``my-tools-v1.0.0.ntp``)."""
    meta = manifest["metadata"]
    return f"{meta['tag']}-v{meta['version']}.ntp"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _find_manifest_root(extract_root: Path) -> Path:
    """Locate the directory containing ``manifest.json`` inside an extraction root."""
    direct = extract_root / TOOL_MANIFEST_FILENAME
    if direct.is_file():
        return extract_root
    manifests = list(extract_root.rglob(TOOL_MANIFEST_FILENAME))
    if len(manifests) != 1:
        raise ValueError("Package must contain exactly one manifest.json")
    return manifests[0].parent


# ---------------------------------------------------------------------------
# Lifecycle functions
# ---------------------------------------------------------------------------


def build_tool_pack(source_path: str, output_dir: str | None = None) -> tuple[Path, dict]:
    """Build a ``.ntp`` tool pack from *source_path*.

    Args:
        source_path: Directory containing ``manifest.json`` and tool files.
        output_dir:  Where to write the ``.ntp`` file (defaults to cwd).

    Returns:
        ``(output_path, manifest)`` tuple.

    Raises:
        ValueError: If the source directory or manifest is invalid.
    """
    package_root = Path(source_path).expanduser().resolve()
    if not package_root.is_dir():
        raise ValueError(f"Path not found: {source_path}")

    validation = validate_tool_manifest_from_path(package_root)
    if validation.errors:
        raise ValueError("Invalid manifest: " + "; ".join(validation.errors))

    out_dir = Path(output_dir).expanduser().resolve() if output_dir else Path.cwd().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    output_file = out_dir / tool_pack_filename(validation.manifest)

    with zipfile.ZipFile(output_file, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for full_path in package_root.rglob("*"):
            if full_path.is_file():
                archive.write(full_path, arcname=str(full_path.relative_to(package_root)))

    return output_file, validation.manifest


def install_tool_pack(package_file: str, config=None) -> dict:
    """Install a ``.ntp`` tool pack.

    Extracts the pack to ``~/.neoflow/tools/{tag}/`` and records it in the
    tool-pack registry.

    Args:
        package_file: Path to a ``.ntp`` file.
        config:       Application config (currently unused; reserved for future
                      unsafe-mode enforcement at install time).

    Returns:
        The registry entry dict for the newly installed pack.

    Raises:
        ValueError: If the file is missing, not a ``.ntp``, has an invalid
                    manifest, or is already installed.
    """
    package_path = Path(package_file).expanduser().resolve()
    if not package_path.is_file():
        raise ValueError(f"File not found: {package_file}")
    if package_path.suffix.lower() != ".ntp":
        raise ValueError("Install only supports .ntp files")

    registry = load_tool_registry()

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        with zipfile.ZipFile(package_path, "r") as archive:
            archive.extractall(temp_root)

        package_root = _find_manifest_root(temp_root)
        validation = validate_tool_manifest_from_path(package_root)
        if validation.errors:
            raise ValueError("Invalid manifest: " + "; ".join(validation.errors))

        manifest = validation.manifest
        metadata_block = manifest["metadata"]
        tag = metadata_block["tag"]

        # Check for duplicate installation
        for entry in registry.get("tool-packs", []):
            if entry.get("tag") == tag:
                raise ValueError(f"Tool pack already installed: {tag}")

        # Extract to ~/.neoflow/tools/{tag}/
        install_dir = get_neoflow_tools_dir() / tag
        if install_dir.exists():
            shutil.rmtree(install_dir)
        install_dir.mkdir(parents=True, exist_ok=True)

        for full_path in package_root.rglob("*"):
            if full_path.is_file():
                rel = full_path.relative_to(package_root)
                dest = install_dir / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(full_path, dest)

    # Install declared dependencies into the active Python environment.
    deps = manifest.get("dependencies") or []
    failed_deps: list[str] = []
    if deps:
        failed_deps = _install_tool_dependencies(deps)

    registry_entry = {
        "name": metadata_block["name"],
        "tag": tag,
        "version": metadata_block["version"],
        "description": metadata_block.get("description", ""),
        "author": metadata_block.get("author", ""),
        "install_path": str(get_neoflow_tools_dir() / tag),
        "dependencies": deps,
    }
    if failed_deps:
        registry_entry["failed_dependencies"] = failed_deps
    registry["tool-packs"].append(registry_entry)
    save_tool_registry(registry)

    return registry_entry


def uninstall_tool_pack(pack_query: str) -> dict:
    """Uninstall a tool pack by tag or name.

    Removes the extracted files from ``~/.neoflow/tools/{tag}/`` and deletes
    the registry entry.

    Args:
        pack_query: The pack ``tag`` (or display ``name``) to uninstall.

    Returns:
        The removed registry entry.

    Raises:
        ValueError: If no matching pack is found.
    """
    registry = load_tool_registry()
    target = pack_query.strip()

    entry: dict | None = None
    for e in registry.get("tool-packs", []):
        if e.get("tag") == target or e.get("name") == target:
            entry = e
            break

    if entry is None:
        raise ValueError(f"Tool pack not found: {pack_query}")

    tag = entry["tag"]
    install_dir = get_neoflow_tools_dir() / tag
    if install_dir.exists():
        shutil.rmtree(install_dir)

    registry["tool-packs"] = [
        e for e in registry.get("tool-packs", []) if e.get("tag") != tag
    ]
    save_tool_registry(registry)

    return entry


def list_tool_packs() -> list[dict]:
    """Return a list of all installed tool pack registry entries."""
    return load_tool_registry().get("tool-packs", [])


def scaffold_tool_pack(
    tool_name: str,
    output_dir: str | None = None,
    force: bool = False,
) -> tuple[Path, dict]:
    """Create a new tool-pack source directory scaffold.

    Args:
        tool_name: Display name for the new tool pack (e.g. "Hello World Tool").
        output_dir: Parent directory to create the scaffold in (defaults to cwd).
        force: Overwrite files if destination directory already exists.

    Returns:
        ``(pack_dir, manifest)`` tuple.

    Raises:
        ValueError: If inputs are invalid or destination exists and ``force=False``.
    """
    display_name = tool_name.strip()
    if not display_name:
        raise ValueError("Tool name cannot be empty")

    tag = _slugify_tool_tag(display_name)
    action_name = _trim_tool_suffix(tag.replace("-", "_"))
    class_name = _to_class_name(_trim_tool_suffix(tag))

    parent = Path(output_dir).expanduser().resolve() if output_dir else Path.cwd().resolve()
    pack_dir = parent / tag
    tools_dir = pack_dir / "tools"
    tool_file_name = f"{action_name}_tool.py"
    tool_file = tools_dir / tool_file_name
    tool_definition_file = tools_dir / "tool_definition.py"
    manifest_file = pack_dir / "manifest.json"
    readme_file = pack_dir / "README.md"

    if pack_dir.exists():
        if not force:
            raise ValueError(
                f"Destination already exists: {pack_dir}. Use --force to overwrite."
            )
        if not pack_dir.is_dir():
            raise ValueError(f"Destination exists and is not a directory: {pack_dir}")
        shutil.rmtree(pack_dir)

    tools_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "metadata": {
            "name": display_name,
            "tag": tag,
            "version": "1.0.0",
            "description": f"Tool pack scaffold for {display_name}.",
            "author": "Your Name",
            "license": "MIT",
        },
        "tools": [f"tools/{tool_file_name}"],
    }

    manifest_file.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    tool_definition_source = '''from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal


class ToolDefinition(ABC):
    """Minimal standalone ToolDefinition contract for tool pack development."""

    name: str
    label: str
    icon: str
    description: str
    security_level: Literal["safe", "approval", "unsafe"] = "safe"
    primary_param: str | None = None

    @abstractmethod
    def execute(self, action: dict, config, **ctx) -> str:
        ...
'''
    tool_definition_file.write_text(tool_definition_source, encoding="utf-8")

    tool_source = f'''from __future__ import annotations

from tool_definition import ToolDefinition


class {class_name}Tool(ToolDefinition):
    name = "{action_name}"
    label = "{display_name}"
    icon = "🧰"
    security_level = "safe"
    primary_param = "input"
    description = """\\
### {action_name}
Scaffolded tool action for {display_name}.
```json
{{"action": "{action_name}", "input": "hello"}}
```
**Optional:** `input` (defaults to `world`)
"""

    def execute(self, action: dict, config, **ctx) -> str:
        value = str(action.get("input", "world")).strip() or "world"
        return f"[{action_name}] Received: {{value}}"


def register_tools() -> list[ToolDefinition]:
    return [{class_name}Tool()]
'''
    tool_file.write_text(tool_source, encoding="utf-8")

    created_on = datetime.now().strftime("%Y-%m-%d")
    readme_source = f"""# {display_name}

Scaffold generated by `neoflow tool new` on {created_on}.

## Files

- `manifest.json` - tool-pack metadata and included Python files
- `tools/tool_definition.py` - standalone ToolDefinition base class (no NeoFlow source import required)
- `tools/{tool_file_name}` - ToolDefinition-based implementation

## Build and install

```bash
neoflow tool validate {tag}
neoflow tool build {tag}
neoflow tool install {tag}-v1.0.0.ntp
```

## Example action

```json
{{"action": "{action_name}", "input": "hello"}}
```
"""
    readme_file.write_text(readme_source, encoding="utf-8")

    return pack_dir, manifest
