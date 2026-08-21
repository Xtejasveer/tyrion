"""Application layer session: harness + tools + JSONL persistence."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from pathlib import Path

from tyrion_agent.events import AgentEvent, MessageEndEvent
from tyrion_agent.harness import AgentHarness, AgentHarnessConfig
from tyrion_agent.provider import ModelProvider
from tyrion_agent.sessions.entries import MessageEntry, SessionInfoEntry
from tyrion_agent.sessions.jsonl import JsonlSessionStorage
from tyrion_agent.sessions.tree import reconstruct_state
from tyrion_agent.tools import AgentTool
from tyrion_coding.system_prompt import assemble_system_prompt
from tyrion_coding.tools import create_coding_tools


def _new_id() -> str:
    return uuid.uuid4().hex


class CodingSession:
    """Owns one conversation on disk and one AgentHarness in memory."""

    def __init__(
        self,
        *,
        cwd: str | Path,
        provider: ModelProvider,
        model: str,
        system: str | None = None,
        storage: JsonlSessionStorage,
        tools: list[AgentTool] | None = None,
        session_id: str | None = None,
        name: str | None = None,
        max_turns: int | None = None,
    ) -> None:
        self.cwd = Path(cwd).resolve()
        self.storage = storage
        self.session_id = session_id or _new_id()
        self.name = name
        self._parent_id: str | None = None
        self._initialized = False
        self._system_override = system

        resolved_tools = tools if tools is not None else create_coding_tools(self.cwd)
        resolved_system = (
            system
            if system is not None
            else assemble_system_prompt(cwd=self.cwd, tools=resolved_tools)
        )

        self.harness = AgentHarness(
            AgentHarnessConfig(
                provider=provider,
                model=model,
                system=resolved_system,
                tools=resolved_tools,
                max_turns=max_turns,
            )
        )
        self.harness.subscribe(self._persist_event)

    def refresh_system_prompt(self) -> None:
        """Rebuild the system prompt from the current project files."""

        if self._system_override is not None:
            self.harness.config.system = self._system_override
            return
        self.harness.config.system = assemble_system_prompt(
            cwd=self.cwd,
            tools=self.harness.config.tools,
        )

    async def start(self) -> None:
        """Create a root SessionInfoEntry, or load an existing file."""

        if self._initialized:
            return

        existing = await self.storage.read_all()
        if not existing:
            info = SessionInfoEntry(
                id=_new_id(),
                parent_id=None,
                session_id=self.session_id,
                name=self.name,
                cwd=str(self.cwd),
                model=self.harness.config.model,
            )
            await self.storage.append(info)
            self._parent_id = info.id
        else:
            state = reconstruct_state(existing)
            self.session_id = state.session_id or self.session_id
            self.name = state.name or self.name
            self._parent_id = state.leaf_id
            if state.messages:
                self.harness.replace_messages(state.messages)

        self.refresh_system_prompt()
        self._initialized = True

    async def resume(self) -> None:
        """Load JSONL into the harness. Call this for --resume"""

        entries = await self.storage.read_all()
        state = reconstruct_state(entries)
        self.session_id = state.session_id or self.session_id
        self.name = state.name or self.name
        self._parent_id = state.leaf_id
        self.harness.replace_messages(state.messages)
        self.refresh_system_prompt()
        self._initialized = True

    async def prompt(self, content: str) -> AsyncIterator[AgentEvent]:
        await self.start()
        async for event in self.harness.prompt(content):
            yield event

    async def continue_(self) -> AsyncIterator[AgentEvent]:
        await self.start()
        async for event in self.harness.continue_():
            yield event

    async def _persist_event(self, event: AgentEvent) -> None:
        if not isinstance(event, MessageEndEvent):
            return
        entry = MessageEntry(
            id=_new_id(),
            parent_id=self._parent_id,
            message=event.message,
        )
        await self.storage.append(entry)
        self._parent_id = entry.id