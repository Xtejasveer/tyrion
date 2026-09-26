"""Deterministic verification hooks - the ground-truth signal

No LLM involved. Each hook takes a workspace path and returns (passed, detail)"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

from evals.sandbox import FIXTURES_DIR

Verifier = Callable[[Path], tuple[bool, str]]

_IGNORED_NAMES = {".eval_session.jsonl"}

def _is_ignored(path: Path) -> bool:
    if path.suffix == ".pyc" or "__pycache__" in path.parts:
        return True
    return path.name in _IGNORED_NAMES

def run_pytest(workspace: Path) -> tuple[bool, str]:
    """True if the fixture's test suite passes after the agent's edits"""
    try:
        proc = subprocess.run(
            ["python", "-m", "pytest", "-q"],
            cwd = workspace,
            capture_output=True,
            text = True,
            timeout=120
        )
    except subprocess.TimeoutExpired:
        return False, "pytest timed out after 120s"
    output = (proc.stdout + proc.stderr).strip()
    return proc.returncode == 0, output[-2000:]

def file_contains(workspace:Path, relpath: str, needle: str) -> tuple[bool, str]:
    """True if a file exists and contains the given substring."""
    target = workspace/relpath 
    if not target.is_file():
        return False, f"missing file: {relpath}"
    text = target.read_text(encoding="utf-8", errors="replace")
    ok = needle in text
    return ok, f"{'found' if ok else 'did not find'} {needle!r} in {relpath}"

def file_excludes(workspace: Path, relpath: str, needle: str) -> tuple[bool, str]:
    """True if a file exists and does NOT contain the substring."""
    target = workspace / relpath
    if not target.is_file():
        return False, f"missing file : {relpath}"
    ok = needle not in target.read_text(encoding = "utf-8", errors = "replace")
    return ok, f"{needle!r} {'absent from' if ok else 'still in'} {relpath}"

def files_unchanged(workspace: Path, fixture: str) -> tuple[bool, str]:
    """True if the workspace matches the original fixture (ignoring caches)"""
    src = FIXTURES_DIR / fixture
    changes: list[str] = []

    for f in src.rglob("*"):
        if f.is_file() and not _is_ignored(f):
            rel = f.relative_to(src)
            target = workspace / rel
            if not target.is_file():
                changes.append(f"deleted {rel}")
            elif target.read_bytes() != f.read_bytes():
                changes.append(f"modified {rel}")

    for f in workspace.rglob("*"):
        if f.is_file() and not _is_ignored(f):
            rel = f.relative_to(workspace)
            if not (src / rel).is_file():
                changes.append(f"added {rel}")

    ok = not changes
    return ok, "no files changed" if ok else ";".join(changes)

def all_of(*verifiers: Verifier) -> Verifier:
    """Combine verifiers; passes only if every one passes."""
    def run(workspace: Path) -> tuple[bool, str]:
        details: list[str] = []
        for verifier in verifiers:
            ok, detail = verifier(workspace)
            details.append(detail)
            if not ok:
                return False, " | ".join(details)
        return True, " | ".join(details)

    return run