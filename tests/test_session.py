from __future__ import annotations

from pathlib import Path

import pytest
import asyncio

from tyrion_agent.messages import AssistantMessage, UserMessage
from tyrion_agent.sessions.entries import LeafEntry, MessageEntry, SessionInfoEntry
from tyrion_agent.sessions.jsonl import JsonlSessionStorage


@pytest.mark.asyncio
async def test_jsonl_round_trip(tmp_path: Path) -> None:
    storage = JsonlSessionStorage(tmp_path / "session.jsonl")
    root = SessionInfoEntry(
        id="root",
        parent_id=None,
        session_id="sess-1",
        name="demo",
        model="gpt-4.1-mini",
    )
    user = MessageEntry(
        id="m1",
        parent_id="root",
        message=UserMessage(content="hello"),
    )
    assistant = MessageEntry(
        id="m2",
        parent_id="m1",
        message=AssistantMessage(content="hi there", model="gpt-4.1-mini"),
    )
    await storage.append(root)
    await storage.append(user)
    await storage.append(assistant)

    loaded = await storage.read_all()
    assert [entry.id for entry in loaded] == ["root", "m1", "m2"]
    assert isinstance(loaded[1].message, UserMessage)
    assert loaded[1].message.content == "hello"


@pytest.mark.asyncio
async def test_branch_reconstruction(tmp_path: Path) -> None:
    storage = JsonlSessionStorage(tmp_path / "session.jsonl")
    await storage.append(SessionInfoEntry(id="root", session_id="sess-1", name="demo"))
    await storage.append(
        MessageEntry(id="a", parent_id="root", message=UserMessage(content="A"))
    )
    await storage.append(
        MessageEntry(id="b", parent_id="a", message=UserMessage(content="B"))
    )
    await storage.append(
        MessageEntry(id="c", parent_id="a", message=UserMessage(content="C"))
    )
    await storage.append(LeafEntry(id="leaf", parent_id="c"))

    state = storage.read_state()
    texts = [
        msg.content
        for msg in state.messages
        if hasattr(msg, "content") and isinstance(msg.content, str)
    ]
    assert texts == ["A", "C"]
    assert state.leaf_id == "c"
    assert state.session_id == "sess-1"