# Medium Tool Pack Sample

This sample adds a practical codebase-inspection action with subprocess execution and safer input handling.

## Purpose

Provide `repo_snapshot` to summarize repository state:

- branch name
- changed file count
- latest commit short hash

## File layout

```text
medium/
├── manifest.json
└── tools/
    ├── tool_definition.py
    └── repo_snapshot_tool.py
```

## Build and install

```bash
neoflow tool validate docs/tools/medium
neoflow tool build docs/tools/medium
neoflow tool install repo-inspector-v1.0.0.ntp
```

## Example action

```json
{"action":"repo_snapshot","path":"."}
```
