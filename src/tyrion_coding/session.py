"""Application layer session: harness + tools + JSONL persistence."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from pathlib import Path

from tyrion_agent.events import AgentEvent, MessageEndEvent
from tyrion_agent.harness import AgentHarness, AgentHarnessConfig
from tyrion_agent.messages import AgentMessage, ToolResultMessage, UserMessage
from tyrion_agent.provider import ModelProvider
from tyrion_agent.provider_events import AssistantErrorEvent, TextDeltaEvent
from tyrion_agent.sessions.entries import (
    CompactionEntry,
    MessageEntry,
    SessionInfoEntry,
)
from tyrion_agent.sessions.jsonl import JsonlSessionStorage
from tyrion_agent.sessions.tree import reconstruct_state
from tyrion_agent.tools import AgentTool
from tyrion_ai.model_limits import get_context_window
from tyrion_coding.context_window import estimate_context_tokens
from tyrion_coding.system_prompt import assemble_system_prompt
from tyrion_coding.tools import create_coding_tools

# How many of the most recent messages compaction leaves untouched.
COMPACTION_KEEP_MESSAGES = 6


def _new_id() -> str:
    return uuid.uuid4().hex


def _compaction_split(messages: list[AgentMessage], keep: int) -> int:
    """Index where the kept tail starts; everything before it gets summarized.

    The tail must not start with a tool result, or its tool call would be
    summarized away and the provider would reject the orphaned result. So the
    split moves earlier until the tail starts at a tool call or a user message.
    Returns 0 when there is nothing to summarize.
    """
    split = len(messages) - keep
    while split > 0 and isinstance(messages[split], ToolResultMessage):
        split -= 1
    return max(split, 0)


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

        resolved_tools = (
            tools if tools is not None else create_coding_tools(self.cwd)
        )
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

    def context_tokens(self) -> int:
        """Tokens the next request will take: real API counts where known, else estimated."""
        return estimate_context_tokens(
            self.harness.config.system,
            list(self.harness.messages),
            self.harness.config.tools,
        )

    def context_limit(self) -> int:
        """Context window size of the current model."""
        return get_context_window(self.harness.config.model)

    def needs_compaction(self, threshold: float = 0.80) -> bool:
        """Check if the session token count exceeds the threshold fraction of context window."""
        return self.context_tokens() >= threshold * self.context_limit()

    async def compact(self) -> None:
        """Replace the oldest part of the transcript with a model-written summary.

        The last few messages are kept as they are. The summarized entries are
        recorded in the CompactionEntry so that rebuilding the session drops them.
        Raises if the summary can't be produced, leaving the transcript untouched.
        """
        # Work from what is saved on disk, since that is what resume() rebuilds.
        state = reconstruct_state(await self.storage.read_all())
        messages = state.messages

        split = _compaction_split(messages, keep=COMPACTION_KEEP_MESSAGES)
        if split <= 0:
            return

        to_summarize = messages[:split]
        replaced_entry_ids = state.message_entry_ids[:split]

        # Serialize history for summary prompt
        history_lines = []
        for msg in to_summarize:
            role = (
                "User"
                if msg.role == "user"
                else (
                    "Assistant" if msg.role == "assistant" else "Tool Result"
                )
            )
            content = getattr(msg, "content", "") or getattr(msg, "text", "")
            if isinstance(content, list):
                content = getattr(msg, "text", "")
            history_lines.append(f"[{role}]: {content}")
        history_text = "\n".join(history_lines)

        summary_prompt = [
            UserMessage(
                content=(
                    "Please provide a concise but thorough summary of the following conversation history, "
                    "focusing on what the user asked, what tools were executed, what code was written/edited, "
                    "and what was accomplished. Your summary will be used as context for continuing this session.\n\n"
                    f"Conversation History to Summarize:\n{history_text}"
                )
            )
        ]

        summary_text = ""
        summary_error: str | None = None
        # Invoke backing provider directly to stream the summary
        async for event in self.harness.config.provider.stream_response(
            model=self.harness.config.model,
            system="You are a helpful assistant. Summarize the conversation history clearly.",
            messages=summary_prompt,
            tools=[],
        ):
            if isinstance(event, TextDeltaEvent):
                summary_text += event.delta
            elif isinstance(event, AssistantErrorEvent):
                summary_error = event.error.error_message or "unknown error"

        # The old messages are about to be dropped from context, so never
        # replace them with an empty or placeholder summary.
        if summary_error is not None:
            raise RuntimeError(f"Could not summarize the conversation: {summary_error}")
        summary_text = summary_text.strip()
        if not summary_text:
            raise RuntimeError("The model returned an empty summary; compaction aborted.")

        # Append CompactionEntry log node
        compaction_entry = CompactionEntry(
            id=_new_id(),
            parent_id=self._parent_id,
            summary=summary_text,
            replaced_entry_ids=replaced_entry_ids,
        )

        await self.storage.append(compaction_entry)
        self._parent_id = compaction_entry.id

        # Reload session path from storage files
        await self.resume()