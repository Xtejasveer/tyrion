"""Isolated, throwaway workspaces so evals never touch the real project.

Tyrion runs bash/edit/write for real, so every task executes insode a fresh copy of its fixture directory"""

from __future__ import annotations

import shutil
from pathlib import Path

EVALS_DIR = Path(__file__).resolve().parent
FIXTURES_DIR = EVALS_DIR/"fixtures"
RUNS_DIR = EVALS_DIR/".runs"

def prepare_workspace(fixture: str, task_id: str) -> Path:
    """Copy a fixture into a clean run directory and return its path."""
    src = FIXTURES_DIR/ fixture
    if not src.is_dir():
        raise FileNotFoundError(f"Fixture not found: {src}")

    dest = RUNS_DIR / task_id
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dest)
    return dest