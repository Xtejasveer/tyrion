"""Discover project context files (AGENTS.md, .agents/)."""

from __future__ import annotations
from pathlib import Path

def walk_project_roots(cwd:str | Path) -> list[Path]:
    """cwd first, then parents, stopping at a .git directory or filesystem root."""

    current = Path(cwd).resolve()
    roots: list[Path] = []
    while True:
        roots.append(current)
        if (current/ ".git").exists():
            break
        parent = current.parent
        if parent == current:
            break
        current = parent
    return roots

def discover_agents_md(cwd: str | Path) -> list[Path]:
    """AGENTS.md files from git root toward cwd so the closest file is last."""
    found: list[Path] =[]
    for root in reversed(walk_project_roots(cwd)):
        candidate = root / "AGENTS.md"
        if candidate.is_file():
            found.append(candidate)
    return found

def load_agents_markdown(cwd:str | Path) -> str:
    chunks: list[str] = []
    for path in discover_agents_md(cwd):
        text  = path.read_text(encoding="utf-8").strip()
        if text:
            chunks.append(f"<!--- {path} ---> \n{text}")
    return "\n\n".join(chunks)