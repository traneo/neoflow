from __future__ import annotations

import re
import subprocess
from pathlib import Path

from release_helpers import gather_repo_facts, format_release_plan
from tool_definition import ToolDefinition


_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")


class ReleasePlanTool(ToolDefinition):
    name = "release_plan"
    label = "Release Plan"
    icon = "📦"
    security_level = "safe"
    primary_param = "version"
    description = """\
### release_plan
Generate a structured release plan using repository state.
```json
{"action": "release_plan", "version": "2.4.0"}
```
"""

    def execute(self, action: dict, config, **ctx) -> str:
        version = str(action.get("version", "")).strip()
        if not _VERSION_RE.match(version):
            return "Error: version must follow semver X.Y.Z"

        repo = Path(str(action.get("path", "."))).resolve()
        facts = gather_repo_facts(repo)
        if facts.get("error"):
            return f"Error: {facts['error']}"

        return format_release_plan(version, facts)


class ReleaseTagCreateTool(ToolDefinition):
    name = "release_tag_create"
    label = "Release Tag Create"
    icon = "🏷️"
    security_level = "unsafe"
    primary_param = "version"
    description = """\
### release_tag_create
Create an annotated git tag for a release.
```json
{"action": "release_tag_create", "version": "2.4.0", "message": "Release 2.4.0"}
```
**Warning:** This mutates git history and is marked `unsafe`.
"""

    def execute(self, action: dict, config, **ctx) -> str:
        version = str(action.get("version", "")).strip()
        message = str(action.get("message", f"Release {version}")).strip()
        if not _VERSION_RE.match(version):
            return "Error: version must follow semver X.Y.Z"

        repo = Path(str(action.get("path", "."))).resolve()
        if not repo.exists() or not repo.is_dir():
            return "Error: repository path does not exist"

        tag = f"v{version}"
        proc = subprocess.run(
            ["git", "tag", "-a", tag, "-m", message],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=12,
        )
        if proc.returncode != 0:
            detail = proc.stderr.strip() or proc.stdout.strip() or "unknown error"
            return f"Error: could not create tag {tag}: {detail}"

        return f"Tag created: {tag}"


def register_tools() -> list[ToolDefinition]:
    return [ReleasePlanTool(), ReleaseTagCreateTool()]
