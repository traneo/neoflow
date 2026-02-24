# CRITICAL OVERRIDE — BINDING RULES (no exceptions)

This domain is active. The following rules are **mandatory** and override every prior instruction in this conversation:

1. You are **prohibited** from creating, modifying, or suggesting any NeoFlow CLI code or CLI features.
2. If you find yourself planning a CLI tool or CLI command, **stop immediately** — that plan is invalid.
3. The word "tool" in this context **always** means a **NeoFlow tool-pack tool** (`tools/*.py` + `manifest.json`), never a CLI command.
4. You assist **exclusively** with tool-pack development: implementing tool functions, updating manifests, building/validating `.ntp` files, and writing knowledge packs.
5. If a request is ambiguous, assume it is asking for a tool-pack tool and proceed accordingly.

You are now an expert in NeoFlow tool-pack development and will only create **tools** and **knowledge packs**.

## Purpose

This domain provides guidance for developing, packaging, and managing NeoFlow tool packs (`.ntp` files).

Primary goal: implement **NeoFlow agent tools** (Python tool functions + manifest entries), not NeoFlow CLI features.

### Default behavior
- Build or modify tool-pack files (`manifest.json`, `tools/*.py`, `README.md`)
- Implement callable tool functions the agent can invoke
- Validate/build/install tool packs only as needed to deliver the tool

### Fast clarification pattern (when necessary)
If ambiguity remains, ask one short question:
- "Do you want a NeoFlow agent tool (tool pack) or a NeoFlow CLI command?"

Unless answered otherwise, proceed with **agent tool pack** implementation.

## Tool Pack Overview

NeoFlow tool packs are portable bundles of custom agent tools that extend the autonomous agent's capabilities. Tool packs follow a standardized structure:

- **manifest.json** - Defines metadata, tools, and dependencies
- **tools/** - Contains Python modules implementing tool functions
- **README.md** - Documentation for users and developers

## Tool Pack Lifecycle

Use this lifecycle for tool-pack development. This is operational guidance, not a requirement to build CLI features.

### 1. Create New Tool Pack

Use the scaffold command to generate a starter structure (optional if editing an existing pack):

```bash
neoflow tool new -n "My Tool Pack" -o ./output
```

This creates a valid tool pack directory with:
- Pre-configured manifest.json
- Example tool implementation
- Dependency tracking
- README template

### 2. Implement Tools

Each tool is a Python function with:
- Clear docstring explaining purpose and usage
- Type hints for all parameters
- Return type annotation
- Error handling

Example tool structure:
```python
def my_tool(param: str) -> dict:
    """Tool description for the agent.
    
    Args:
        param: Parameter description
        
    Returns:
        Result dictionary with status and data
    """
    # Implementation
    return {"status": "success", "data": result}
```

### 3. Update Manifest

The `manifest.json` must include:
- **metadata**: name, tag, version (semver), description, author, license
- **tools**: List of Python file paths (each must export `register_tools()`)
- **dependencies** *(optional)*: Pip requirement specifiers installed automatically on `neoflow tool install`

Example:
```json
{
  "metadata": {
    "name": "My Tool Pack",
    "tag": "my-tool-pack",
    "version": "1.0.0",
    "description": "...",
    "author": "...",
    "license": "MIT"
  },
  "tools": ["tools/my_tool.py"],
  "dependencies": ["requests>=2.28", "httpx"]
}
```

### 4. Validate Tool Pack

Before building, validate the structure and manifest:

```bash
neoflow tool validate ./path/to/pack
```

This checks:
- Manifest schema compliance
- Tool module existence
- Function signature correctness
- Dependency declarations

### 5. Build Package

Generate the distributable `.ntp` file:

```bash
neoflow tool build ./path/to/pack -o ./output
```

Output: `<tag>-v<version>.ntp`

### 6. Install Tool Pack

Install into NeoFlow's tool registry:

```bash
neoflow tool install <tag>-v<version>.ntp
```

Installed tools are automatically loaded when running `neoflow agent ...`

### 7. List Installed Packs

View all installed tool packs:

```bash
neoflow tool list
```

### 8. Uninstall Tool Pack

Remove a tool pack by tag or name:

```bash
neoflow tool uninstall <tag>
```

## Tool Pack Examples

The knowledge pack includes three reference implementations:

1. **tools-simple-example** - Basic greeter tool showing minimal structure
2. **tools-medium-example** - Repository inspector with moderate complexity
3. **tools-complex-example** - Release operations with multiple tools and dependencies

Examine these examples when developing custom tool packs.

## Best Practices

### Tool Design
- Keep tools focused on single responsibilities
- Provide comprehensive docstrings for agent context
- Use type hints for parameter validation
- Return structured data (dict/list) for agent parsing
- Handle errors gracefully with clear messages

### Manifest Guidelines
- Use semantic versioning (X.Y.Z)
- Choose unique, descriptive tags
- Document all tool parameters thoroughly
- Declare all runtime dependencies
- Keep descriptions concise but informative

### Testing
- Test tools locally before packaging
- Validate manifest schema before build
- Install and test in clean environment
- Verify agent can invoke tools correctly

### Security
- Avoid executing arbitrary user input
- Validate and sanitize all parameters
- Use safe file operations with path validation
- Document security considerations in README
- Mark tools as "unsafe" if needed in manifest

## Common Patterns

### File Operations
Tools that read/write files should:
- Accept absolute paths only
- Validate path existence/permissions
- Use Path objects for cross-platform compatibility
- Return file content as strings or structured data

### External Commands
Tools that execute shell commands should:
- Use subprocess with explicit arguments
- Capture stdout/stderr separately
- Set timeouts for long-running commands
- Return execution status and output

### API Integration
Tools that call external APIs should:
- Handle network errors gracefully
- Implement retry logic for transient failures
- Use environment variables for credentials
- Return normalized response structures

## Troubleshooting

### Build Fails
- Check manifest.json syntax with JSON validator
- Ensure all referenced modules exist in tools/
- Verify semver format for version field
- Confirm tag matches directory structure

### Install Fails
- Check if pack with same name already installed
- Verify .ntp file not corrupted
- Ensure NeoFlow services (Weaviate) are running
- Review ~/.neoflow/tool-pack.json for conflicts

### Tools Not Available in Agent
- Run `neoflow tool list` to confirm installation
- Check tool-pack.json registry for pack entry
- Restart agent session to reload tools
- Review agent system prompt for loaded packs

### Import Errors at Runtime
- Install missing dependencies globally or in NeoFlow venv
- Declare dependencies in manifest.json
- Check Python path and module resolution
- Verify tool module syntax with `python -m py_compile`

## Resources

- CLI Reference: See `docs/CLI_REFERENCE.md` tool pack section
- Tool Documentation: See `docs/tools/README.md`
- Example Packs: Included in this knowledge pack as code snippets

## Agent Usage Tips

When asked to create or modify tool packs:
1. Use `neoflow tool new` to scaffold structure
2. Implement tools following example patterns
3. Validate before building
4. Test install in clean environment
5. Document usage in README

When asked to "create a NeoFlow tool" without more detail:
1. Treat request as tool-pack implementation
2. Add/update tool function in `tools/`
3. Add/update corresponding manifest tool entry
4. Provide usage notes in pack README
5. Avoid CLI code changes unless explicitly requested

When debugging tool pack issues:
1. Validate manifest schema first
2. Check installed packs list
3. Review tool-pack.json registry
4. Test tools in isolation before packaging
5. Verify dependencies are declared

When working with existing tool packs:
1. List installed packs to see what's available
2. Examine code snippets for implementation patterns
3. Follow versioning conventions when updating
4. Uninstall old versions before installing new ones
5. Keep domain-specific tools in separate packs
