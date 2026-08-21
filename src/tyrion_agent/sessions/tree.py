"""Reconstruct a linear branch from a flat parent-pointer log."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from tyrion_agent.messages import AgentMessage
from tyrion_agent.sessions.entries import (
    LeafEntry,
    MessageEntry,
    ModelChangeEntry,
    SessionInfoEntry,
    SessionEntry,
)

@dataclass(slots=True)
class SessionState:
    """Rebuilt view of one branch of a session."""

    session_id : str | None = None
    name: str | None = None
    cwd : str | None = None
    model: str | None = None
    leaf_id : str | None = None
    entries : list[SessionEntry] = field(default_factory=list)
    messages : list[AgentMessage] = field(default_factory=list)

def index_entries(entries: Sequence[SessionEntry]) -> dict[str, SessionEntry]:
    return {entry.id: entry for entry in entries}

def find_leaf_id(entries: Sequence[SessionEntry]) -> str | None:
    """Latest LeafEntry wins; otherwise the last entry in the file."""

    leaf_id : str | None = None
    for entry in entries:
        if isinstance(entry, LeafEntry) and entry.parent_id is not None:
            leaf_id = entry.parent_id
    if leaf_id is not None:
        return leaf_id
    if entries:
        return entries[-1].id
    return None

def reconstruct_path(
        entries :Sequence[SessionEntry],
        *,
        leaf_id: str |None = None,
) -> list[SessionEntry]:
    """Walk parent pointers from a leaf back to the root, then reverse"""

    by_id = index_entries(entries)
    current_id = leaf_id if leaf_id is not None else find_leaf_id(entries)
    path : list[SessionEntry] =[]
    seen: set[str] = set()

    while current_id is not None and current_id not in seen:
        seen.add(current_id)
        entry = by_id.get(current_id)
        if entry is None:
            break
        path.append(entry)
        current_id = entry.parent_id
    path.reverse()
    return path

def reconstruct_state(
        entries: Sequence[SessionEntry],
        *,
        leaf_id: str |None = None,
) -> SessionState:
    """Build SessionState for one branch."""
    path = reconstruct_path(entries, leaf_id=leaf_id)
    state = SessionState(entries=list(path), leaf_id=path[-1].id if path else None)

    for entry in path:
        if isinstance(entry, SessionInfoEntry):
            state.session_id = entry.session_id
            if entry.name is not None:
                state.name = entry.name
            if entry.cwd is not None:
                state.cwd = entry.cwd
            if entry.model is not None:
                state.model = entry.model
        elif isinstance(entry, ModelChangeEntry):
            state.model = entry.model
        elif isinstance(entry, MessageEntry):
            state.messages.append(entry.message)

    return state
    
