# Tool Packs Documentation

This guide covers NeoFlow custom tool packs (`.ntp`), including lifecycle, manifest schema, tool contract, security behavior, and production-ready examples.

## What is a Tool Pack?

A tool pack is a zip archive with `.ntp` extension that contains:

- `manifest.json` with metadata and tool file list
- One or more Python files under `tools/`
- A `register_tools()` function in each listed tool file

Installed tool packs are loaded automatically by `neoflow agent` and appended to the agent prompt under **Installed Tool Packs**.

## Lifecycle

### 1) Scaffold

```bash
neoflow tool new -n "My Tool Pack"
```

### 2) Implement tools

Edit generated files under `<tag>/tools/`.

### 3) Validate

```bash
neoflow tool validate <tag>
```

### 4) Build package

```bash
neoflow tool build <tag>
# => <tag>-v1.0.0.ntp
```

### 5) Install package

```bash
neoflow tool install <tag>-v1.0.0.ntp
```

### 6) Verify / remove

```bash
neoflow tool list
neoflow tool uninstall <tag>
```

## Manifest Schema

`manifest.json` must follow:

```json
{
  "metadata": {
    "name": "My Tool Pack",
    "tag": "my-tool-pack",
    "version": "1.0.0",
    "description": "Custom tools for NeoFlow agent.",
    "author": "Your Name",
    "license": "MIT"
  },
  "tools": [
    "tools/example_tool.py"
  ],
  "dependencies": [
    "requests>=2.28",
    "httpx"
  ]
}
```

### Validation rules

- `metadata.name`, `tag`, `version`, `description`, `author`, `license` are required
- `metadata.version` must be semver: `X.Y.Z`
- `tools` must be a list of existing Python file paths
- `dependencies` is optional; if present, must be a list of non-empty pip requirement specifiers

## Dependencies

Tool packs can declare Python package requirements via the optional `dependencies` field.

**Behaviour at install time:**

- Each entry is installed with `sys.executable -m pip install <dep>` — no `--break-system-packages` or system-level overrides are used.
- Packages install into the Python environment neoflow is running in (typically its own venv).
- If any package fails to install, the pack is still registered and the failed specifiers are recorded in `~/.neoflow/tool-pack.json` under `failed_dependencies` for that entry.

**At uninstall time:**

- Dependencies are **not** removed automatically; other packs or the user may rely on them.

**Example:**

```json
"dependencies": ["requests>=2.28", "boto3", "pydantic>=2"]
```

## Tool Contract

Each tool class must implement the same contract:

```python
class ToolDefinition(ABC):
    name: str
    label: str
    icon: str
    description: str
    security_level: Literal["safe", "approval", "unsafe"] = "safe"
    primary_param: str | None = None

    @abstractmethod
    def execute(self, action: dict, config, **ctx) -> str:
        ...
```

Each listed module must expose:

```python
def register_tools() -> list[ToolDefinition]:
    return [MyTool()]
```

## Naming and Registration Rules

- Tool name must match: `^[a-z][a-z0-9_]*$`
- Built-in names are reserved and cannot be overridden
  - Examples: `run_command`, `read_file`, `edit_file`, `search_code`, `ask_chat`, `done`
- Duplicate / invalid tools are skipped with warnings during load

## Security Model

- `safe`: always load
- `approval`: tool declares elevated behavior but no automatic prompt UI is enforced by registry itself
- `unsafe`: loaded only when `AGENT_UNSAFE_MODE=true`

Notes:
- install-time policy does not currently block `unsafe` tools
- runtime loading is where unsafe tools are gated

## Installation Locations

NeoFlow stores tool packs in user home resources:

- Registry: `~/.neoflow/tool-pack.json`
- Extracted packs: `~/.neoflow/tools/<tag>/`

## Best Practices

- Keep `execute()` deterministic and return clear text results
- Validate inputs from `action` before side effects
- Prefer bounded operations and explicit timeouts for subprocess work
- Keep descriptions concise and include JSON usage examples
- Use unique, domain-specific tool names

## Sample Packs

Three full reference samples are included:

- [Simple Sample](simple/README.md)
- [Medium Sample](medium/README.md)
- [Complex Sample](complex/README.md)
