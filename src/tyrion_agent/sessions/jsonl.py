"""JSONL session storage. Append-only; never rewrite old lines."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from pydantic import TypeAdapter

from tyrion_agent.sessions.entries import SessionEntry
from tyrion_agent.sessions.tree import SessionState, reconstruct_state

SESSION_ENTRY_ADAPTER: TypeAdapter[SessionEntry] = TypeAdapter(SessionEntry)

class SessionStorage(Protocol):
    """Storage contract used by the coding-app session wrapper."""

    async def append(self, entry:SessionEntry) -> None: ...

    async def read_all(self) -> list[SessionEntry]: ...

    def read_state(self, *, leaf_id: str | None = None) -> SessionState: ...

class JsonlSessionStorage:
    """One '.jsonl' file per session."""

    def __init__(self, path:Path) -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    async def append(self, entry: SessionEntry) -> None:
        self._path.parent.mkdir(parents= True, exist_ok = True)
        line = entry.model_dump_json() + "\n"
        with self._path.open("a", encoding = "utf-8") as handle:
            handle.write(line)

    async def read_all(self) -> list[SessionEntry]:
        if not self._path.exists():
            return[]
        entries: list[SessionEntry] =[]
        with self._path.open("r", encoding = "utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                entries.append(SESSION_ENTRY_ADAPTER.validate_json(line))
        return entries
    
    def read_state(self,*, leaf_id: str | None = None) -> SessionState:
        if not self._path.exists():
            return SessionState()
        entries:list[SessionEntry] = []
        with self._path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                entries.append(SESSION_ENTRY_ADAPTER.validate_json(line))
        return reconstruct_state(entries,leaf_id=leaf_id)

    async def append_many(self, entries: Sequence[SessionEntry]) -> None:
        for entry in entries:
            await self.append(entry)
