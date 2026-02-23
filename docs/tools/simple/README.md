# Simple Tool Pack Sample

This sample shows the smallest practical custom tool pack.

## Purpose

Add one lightweight action `say_hello` that returns a greeting.

## File layout

```text
simple/
├── manifest.json
└── tools/
    ├── tool_definition.py
    └── say_hello_tool.py
```

## Build and install

```bash
neoflow tool validate docs/tools/simple
neoflow tool build docs/tools/simple
neoflow tool install simple-greeter-v1.0.0.ntp
```

## Example action

```json
{"action":"say_hello","name":"NeoFlow"}
```
