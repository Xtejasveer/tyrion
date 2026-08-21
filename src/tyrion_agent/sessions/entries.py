"""Append-only session log entries.

Each entry is a node in a parent-pointer tree. Sessions never rewrite ols lines:
branches are created by appending a new child under an earlier parent."""

from __future__ import annotations

from typing import Annotated, Literal
from pydantic import Field

from tyrion_agent.messages import AgentMessage, WireModel, current_timestamp_ms

class SessionEntryBase(WireModel):
    """Fields shared by every session log entry."""

    id: str
    parent_id :str | None = None
    timestamp : int = Field(default_factory=current_timestamp_ms)

class MessageEntry(SessionEntryBase):
    """A transcript message that completed (user, assistant, or tool result)."""

    type: Literal["message"] = "message"
    message: AgentMessage

class ModelChangeEntry(SessionEntryBase):
    """A model was switched mid-session"""

    type: Literal["model_change"] = "model_change"
    model : str

class CompactionEntry(SessionEntryBase):
    """Oldest transcript messages were replaced by a summary"""

    type: Literal["compaction"] = "compaction"
    summary: str
    replaced_entry_ids : list[str] = Field(default_factory=list)

class LabelEntry(SessionEntryBase):
    """User-assigned bookmark on a branch."""
    type: Literal["label"] = "label"
    label: str

class LeafEntry(SessionEntryBase):
    """Marks the current branch head.
    'parent_id' is the id of the entry that is now the leaf.
    """

    type: Literal["leaf"] = "leaf"

class SessionInfoEntry(SessionEntryBase):
    """Session metadata. Typically the root ('parent_id = None')."""

    type: Literal["session_info"] = "session_info"
    session_id : str
    name: str | None= None
    cwd : str | None = None
    model : str | None = None

type SessionEntry = Annotated[
    MessageEntry
    | ModelChangeEntry
    | CompactionEntry
    | LabelEntry
    | LeafEntry
    | SessionInfoEntry,
    Field(discriminator="type")
]