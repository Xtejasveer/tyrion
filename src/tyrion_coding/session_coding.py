"""Create, list, and load Tyrion sessions on disk."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from tyrion_agent.sessions.jsonl import JsonlSessionStorage
from tyrion_agent.sessions.tree import reconstruct_state


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
                    path = Path,
                    name = state.name,
                    model = state.model,
                    created_at=created_at,
                    message_count=len(state.messages),
                )
            )
            return metas