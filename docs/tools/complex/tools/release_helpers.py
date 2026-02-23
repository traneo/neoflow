from __future__ import annotations

import json
import subprocess
from pathlib import Path


def _run(cmd: list[str], cwd: Path) -> tuple[int, str, str]:
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=12)
    return p.returncode, p.stdout.strip(), p.stderr.strip()


def gather_repo_facts(repo_path: Path) -> dict:
    rc, branch, _ = _run(["git", "branch", "--show-current"], repo_path)
    if rc != 0:
        return {"error": "not a git repository"}

    _, head, _ = _run(["git", "rev-parse", "--short", "HEAD"], repo_path)
    _, status, _ = _run(["git", "status", "--porcelain"], repo_path)

    changed = 0 if not status else len(status.splitlines())
    return {
        "repository": str(repo_path),
        "branch": branch or "(detached)",
        "head": head or "unknown",
        "changed_files": changed,
    }


def format_release_plan(version: str, facts: dict) -> str:
    payload = {
        "release_version": version,
        "preflight": facts,
        "checklist": [
            "Run full test suite",
            "Update changelog",
            "Verify migration notes",
            "Create release tag",
            "Publish artifacts",
        ],
    }
    return json.dumps(payload, indent=2)
