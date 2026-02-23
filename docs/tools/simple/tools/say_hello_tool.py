from __future__ import annotations

from tool_definition import ToolDefinition


class SayHelloTool(ToolDefinition):
    name = "say_hello"
    label = "Say Hello"
    icon = "👋"
    security_level = "safe"
    primary_param = "name"
    description = """\
### say_hello
Return a friendly greeting.
```json
{"action": "say_hello", "name": "NeoFlow"}
```
"""

    def execute(self, action: dict, config, **ctx) -> str:
        name = str(action.get("name", "world")).strip() or "world"
        return f"Hello, {name}!"


def register_tools() -> list[ToolDefinition]:
    return [SayHelloTool()]
