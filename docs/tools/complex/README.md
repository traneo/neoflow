# Complex Tool Pack Sample

This sample demonstrates a multi-tool pack with shared helper logic, structured JSON output, and one unsafe action.

## Purpose

Provide two actions:

1. `release_plan` (safe): inspect repo metadata and generate a release checklist
2. `release_tag_create` (unsafe): create an annotated git tag

## File layout

```text
complex/
├── manifest.json
└── tools/
    ├── tool_definition.py
    ├── release_helpers.py
    └── release_tools.py
```

## Build and install

```bash
neoflow tool validate docs/tools/complex
neoflow tool build docs/tools/complex
neoflow tool install release-ops-v1.0.0.ntp
```

## Example actions

```json
{"action":"release_plan","version":"2.4.0"}
```

```json
{"action":"release_tag_create","version":"2.4.0","message":"Release 2.4.0"}
```

## Security note

`release_tag_create` is marked `security_level = "unsafe"`.
It loads only when `AGENT_UNSAFE_MODE=true`.
