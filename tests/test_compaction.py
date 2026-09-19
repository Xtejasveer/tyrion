"""Compaction: the summary must replace the old messages, not sit beside them."""

from __future__ import annotations

from pathlib import Path

import pytest

from tyrion_agent.messages import (
    AssistantMessage,
    TextContent,
    ToolCall,
    ToolResultMessage,
    UserMessage,
)
from tyrion_agent.provider_events import (
    AssistantDoneEvent,
    AssistantErrorEvent,
    AssistantStartEvent,
    TextDeltaEvent,
)
from tyrion_agent.sessions.entries import (
    CompactionEntry,
    MessageEntry,
    SessionInfoEntry,
)
from tyrion_agent.sessions.tree import reconstruct_state
from tyrion_ai.fake import FakeProvider
from tyrion_coding.session import CodingSession, _compaction_split
from tyrion_coding.session_coding import SessionManager


def _text_stream(text: str, model: str = "fake-model") -> list:
    message = AssistantMessage(content=text, model=model)
    return [
        AssistantStartEvent(partial=AssistantMessage(model=model)),
        TextDeltaEvent(delta=text, partial=message),
        AssistantDoneEvent(message=message),
    ]


def _chain(*entries) -> list:
    """Link entries into one branch: each entry's parent is the one before it."""
    linked, parent = [], None
    for entry in entries:
        entry.parent_id = parent
        parent = entry.id
        linked.append(entry)
    return linked


def _msg(entry_id: str) -> MessageEntry:
    return MessageEntry(id=entry_id, message=UserMessage(content=entry_id))


def _contents(state) -> list[str]:
    return [msg.content for msg in state.messages]


# --- rebuilding a session ----------------------------------------------------


def test_compaction_drops_the_messages_it_replaced() -> None:
    entries = _chain(
        SessionInfoEntry(id="root", session_id="s"),
        *[_msg(f"m{i}") for i in range(1, 9)],
        CompactionEntry(id="c1", summary="SUMMARY", replaced_entry_ids=[f"m{i}" for i in range(1, 6)]),
    )

    state = reconstruct_state(entries)

    assert len(state.messages) == 4  # summary + the 3 kept messages
    assert "SUMMARY" in state.messages[0].content  # summary comes first
    assert _contents(state)[1:] == ["m6", "m7", "m8"]
    assert state.message_entry_ids == ["c1", "m6", "m7", "m8"]


def test_a_second_compaction_replaces_the_first_summary() -> None:
    entries = _chain(
        SessionInfoEntry(id="root", session_id="s"),
        *[_msg(f"m{i}") for i in range(1, 9)],
        CompactionEntry(id="c1", summary="FIRST", replaced_entry_ids=[f"m{i}" for i in range(1, 6)]),
        _msg("m9"),
        _msg("m10"),
        CompactionEntry(id="c2", summary="SECOND", replaced_entry_ids=["c1", "m6", "m7", "m8"]),
    )

    state = reconstruct_state(entries)

    assert _contents(state)[1:] == ["m9", "m10"]
    assert "SECOND" in state.messages[0].content
    assert all("FIRST" not in content for content in _contents(state))


def test_split_never_leaves_a_tool_result_without_its_tool_call() -> None:
    messages = [
        UserMessage(content="u1"),
        AssistantMessage(content=[ToolCall(id="c1", name="read")], stop_reason="toolUse"),
        ToolResultMessage(tool_call_id="c1", tool_name="read", content=[TextContent(text="r")]),
        UserMessage(content="u2"),
        AssistantMessage(content="a2"),
        UserMessage(content="u3"),
    ]

    assert _compaction_split(messages, keep=3) == 3  # tail starts at a user message
    assert _compaction_split(messages, keep=4) == 1  # would start at the result -> back up to the call
    assert _compaction_split(messages, keep=6) == 0  # nothing to summarize


# --- CodingSession.compact() -------------------------------------------------


async def _session_with_history(tmp_path: Path, extra_streams: list) -> CodingSession:
    manager = SessionManager(root=tmp_path)
    session_id, storage = manager.new_storage()
    provider = FakeProvider([_text_stream(f"answer {i}") for i in range(1, 6)] + extra_streams)
    session = CodingSession(
        cwd=tmp_path,
        provider=provider,
        model="fake-model",
        system="test",
        storage=storage,
        session_id=session_id,
        tools=[],
    )
    for i in range(1, 6):
        async for _event in session.prompt(f"question {i}"):
            pass
    return session


@pytest.mark.asyncio
async def test_compact_shrinks_the_transcript(tmp_path: Path) -> None:
    session = await _session_with_history(tmp_path, [_text_stream("THE SUMMARY")])
    assert len(session.harness.messages) == 10

    await session.compact()

    messages = session.harness.messages
    assert len(messages) == 7  # the summary + the last 6 messages
    assert "THE SUMMARY" in messages[0].content
    kept_questions = [m.content for m in messages[1:] if isinstance(m, UserMessage)]
    assert kept_questions == ["question 3", "question 4", "question 5"]
    # ...and it stays small when the session is reloaded from disk.
    assert len(session.storage.read_state().messages) == 7


@pytest.mark.asyncio
async def test_failed_summary_leaves_the_transcript_untouched(tmp_path: Path) -> None:
    failure = AssistantMessage(content=[], stop_reason="error", error_message="boom")
    session = await _session_with_history(tmp_path, [[AssistantErrorEvent(error=failure)]])

    with pytest.raises(RuntimeError, match="boom"):
        await session.compact()

    assert len(session.harness.messages) == 10
    assert len(session.storage.read_state().messages) == 10
