"""Reconstruct a linear branch from a flat parent-pointer log."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from tyrion_agent.messages import AgentMessage, AssistantMessage, UserMessage
from tyrion_agent.sessions.entries import (
    CompactionEntry,
    LeafEntry,
    MessageEntry,
    ModelChangeEntry,
    SessionEntry,
    SessionInfoEntry,
)


@dataclass(slots=True)
class SessionState:
    """Rebuilt view of one branch of a session."""

    session_id: str | None = None
    name: str | None = None
    cwd: str | None = None
    model: str | None = None
    leaf_id: str | None = None
    entries: list[SessionEntry] = field(default_factory=list)
    messages: list[AgentMessage] = field(default_factory=list)
    # Log entry id behind each item in `messages` (same length, same order).
    # A compaction summary is identified by its CompactionEntry id.
    message_entry_ids: list[str] = field(default_factory=list)


def _without_usage(message: AgentMessage) -> AgentMessage:
    """Drop the API token counts from an assistant message.

    Those counts described the prompt as it was before a compaction shortened it,
    so they no longer say how big the context is.
    """
    if isinstance(message, AssistantMessage) and message.usage:
        return message.model_copy(update={"usage": {}})
    return message


def index_entries(entries: Sequence[SessionEntry]) -> dict[str, SessionEntry]:
    return {entry.id: entry for entry in entries}


def find_leaf_id(entries: Sequence[SessionEntry]) -> str | None:
    """Latest LeafEntry wins; otherwise the last entry in the file."""
    leaf_id: str | None = None
    for entry in entries:
        if isinstance(entry, LeafEntry) and entry.parent_id is not None:
            leaf_id = entry.parent_id
    if leaf_id is not None:
        return leaf_id
    if entries:
        return entries[-1].id
    return None


def reconstruct_path(
    entries: Sequence[SessionEntry],
    *,
    leaf_id: str | None = None,
) -> list[SessionEntry]:
    """Walk parent pointers from a leaf back to the root, then reverse"""
    by_id = index_entries(entries)
    current_id = leaf_id if leaf_id is not None else find_leaf_id(entries)
    path: list[SessionEntry] = []
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
    leaf_id: str | None = None,
) -> SessionState:
    """Build SessionState for one branch."""
    path = reconstruct_path(entries, leaf_id=leaf_id)
    state = SessionState(
        entries=list(path), leaf_id=path[-1].id if path else None
    )

    # (entry id, message) pairs, so a compaction can drop the messages it replaced.
    pairs: list[tuple[str, AgentMessage]] = []

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
            pairs.append((entry.id, entry.message))
        elif isinstance(entry, CompactionEntry):
            # The summary stands in for the messages it replaced: drop those
            # and put the summary first, ahead of the messages that were kept.
            replaced = set(entry.replaced_entry_ids)
            kept = [
                (entry_id, _without_usage(msg))
                for entry_id, msg in pairs
                if entry_id not in replaced
            ]
            summary = UserMessage(
                content=(
                    "System Notification: The preceding conversation history "
                    "has been compacted. Summary of past events:\n\n"
                    f"{entry.summary}"
                )
            )
            pairs = [(entry.id, summary), *kept]

    state.messages = [msg for _, msg in pairs]
    state.message_entry_ids = [entry_id for entry_id, _ in pairs]
    return state