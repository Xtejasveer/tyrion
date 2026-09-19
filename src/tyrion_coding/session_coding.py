"""Create, list, and load Tyrion sessions on disk."""

from __future__ import annotations

import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from tyrion_agent.messages import UserMessage
from tyrion_agent.sessions.entries import MessageEntry, SessionEntry
from tyrion_agent.sessions.jsonl import JsonlSessionStorage
from tyrion_coding.display import one_line


def default_sessions_dir() -> Path:
    return Path.home() / ".tyrion" / "sessions"

@dataclass(slots=True)
class SessionMeta:
    session_id: str
    path: Path
    name: str | None
    model: str | None
    created_at: datetime | None
    message_count: int
    title: str | None = None  # what the chat is about: the first thing the user asked


# Words that make a short message small talk ("hello", "say hi", "hey Tyrion")
# rather than a task, so it says nothing about what the chat was for.
_SMALL_TALK = frozenset({
    "hi", "hello", "hey", "hiya", "yo", "sup", "hola", "howdy", "there", "tyrion", "test",
    "testing", "ping", "thanks", "thank", "you", "ok", "okay", "say", "good", "morning",
    "afternoon", "evening",
})  # fmt: skip


def _is_small_talk(text: str) -> bool:
    words = re.findall(r"[a-z']+", text.lower())
    return 0 < len(words) <= 4 and all(word in _SMALL_TALK for word in words)


def first_prompt(entries: Sequence[SessionEntry]) -> str | None:
    """What a chat was about: the first real thing the user asked, as one line.

    A greeting like "hello" is skipped in favour of the first actual request. If
    the user never asked for anything but small talk, that is used. None if they
    never wrote anything.

    Read from the log entries rather than the rebuilt transcript: after a
    compaction the first messages are replaced by a summary, but they are still
    what the chat was originally about.
    """
    first: str | None = None
    for entry in entries:
        if isinstance(entry, MessageEntry) and isinstance(entry.message, UserMessage):
            text = one_line(entry.message.content)
            if not text:
                continue
            if not _is_small_talk(text):
                return text
            first = first or text
    return first


class SessionManager:
    def __init__(self, root:Path | None = None) -> None:
        self.root = root or default_sessions_dir()
        self.root.mkdir(parents=True, exist_ok=True)

    def new_storage(
        self, session_id: str | None = None
    ) -> tuple[str, JsonlSessionStorage]:
        sid = session_id or uuid.uuid4().hex
        return sid, JsonlSessionStorage(self.root / f"{sid}.jsonl")
    
    def storage_for(self, session_id: str) -> JsonlSessionStorage:
        return JsonlSessionStorage(self.root / f"{session_id}.jsonl")

    def list_sessions(self) ->list[SessionMeta]:
        metas: list[SessionMeta] = []
        for path in sorted(self.root.glob("*.jsonl")):
            try:
                state = JsonlSessionStorage(path).read_state()
            except Exception:
                continue
            created_at:datetime| None =None
            if state.entries:
                created_at = datetime.fromtimestamp(
                    state.entries[0].timestamp/1000,
                    tz = timezone.utc,
                )
            metas.append(
                SessionMeta(
                    session_id=state.session_id or path.stem,
                    path = path,
                    name = state.name,
                    model = state.model,
                    created_at=created_at,
                    message_count=len(state.messages),
                    title=first_prompt(state.entries),
                )
            )
        return metas