from __future__ import annotations

import subprocess
from pathlib import Path

from tool_definition import ToolDefinition


class RepoSnapshotTool(ToolDefinition):
    name = "repo_snapshot"
    label = "Repo Snapshot"
    icon = "🧭"
    security_level = "approval"
    primary_param = "path"
    description = """\
### repo_snapshot
Return a compact git repository status summary.
```json
{"action": "repo_snapshot", "path": "."}
```
**Optional:** `path` (defaults to current directory)
"""

    def execute(self, action: dict, config, **ctx) -> str:
        raw_path = str(action.get("path", ".")).strip() or "."
        repo = Path(raw_path).resolve()
        if not repo.exists() or not repo.is_dir():
            return f"Error: directory not found: {raw_path}"

        def run(cmd: list[str]) -> tuple[int, str, str]:
            p = subprocess.run(cmd, cwd=repo, capture_output=True, text=True, timeout=8)
            return p.returncode, p.stdout.strip(), p.stderr.strip()

        rc, branch, _ = run(["git", "branch", "--show-current"])
        if rc != 0:
            return "Error: target is not a git repository or git is unavailable."

        _, commit, _ = run(["git", "rev-parse", "--short", "HEAD"])
        _, status, _ = run(["git", "status", "--porcelain"])

        changed = 0 if not status else len(status.splitlines())
        return (
            f"Repository: {repo}\n"
            f"Branch: {branch or '(detached)'}\n"
            f"HEAD: {commit or 'unknown'}\n"
            f"Changed files: {changed}"
        )


def register_tools() -> list[ToolDefinition]:
    return [RepoSnapshotTool()]
