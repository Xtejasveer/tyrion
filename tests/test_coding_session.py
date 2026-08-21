from __future__ import annotations

from pathlib import Path

import pytest

from tyrion_agent.messages import AssistantMessage, UserMessage
from tyrion_agent.provider_events import (
    AssistantDoneEvent,
    AssistantStartEvent,
    TextDeltaEvent,
)
from tyrion_ai.fake import FakeProvider
from tyrion_coding.session import CodingSession
from tyrion_coding.session_coding import SessionManager


def _text_stream(text: str, model: str = "fake-model") -> list:
    message = AssistantMessage(content=text, model=model)
    return [
        AssistantStartEvent(partial=AssistantMessage(model=model)),
        TextDeltaEvent(delta=text, partial=message),
        AssistantDoneEvent(message=message),
    ]


@pytest.mark.asyncio
async def test_prompt_persists_and_resume_restores(tmp_path: Path) -> None:
    manager = SessionManager(root=tmp_path)
    session_id, storage = manager.new_storage()
    provider = FakeProvider(
        [
            _text_stream("hello from the agent"),
            _text_stream("and this is a follow-up"),
        ]
    )

    session = CodingSession(
        cwd=tmp_path,
        provider=provider,
        model="fake-model",
        system="You are a test agent.",
        storage=storage,
        session_id=session_id,
        tools=[],
    )

    async for _event in session.prompt("hi"):
        pass

    roles = [msg.role for msg in session.harness.messages]
    assert roles[0] == "user"
    assert roles[1] == "assistant"
    assert isinstance(session.harness.messages[0], UserMessage)
    assert session.harness.messages[0].content == "hi"

    restored = CodingSession(
        cwd=tmp_path,
        provider=provider,
        model="fake-model",
        system="You are a test agent.",
        storage=storage,
        session_id=session_id,
        tools=[],
    )
    await restored.resume()
    assert [msg.role for msg in restored.harness.messages] == ["user", "assistant"]
    assert restored.harness.messages[0].content == "hi"

    async for _event in restored.prompt("continue please"):
        pass

    assert [msg.role for msg in restored.harness.messages] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]

    listed = manager.list_sessions()
    assert len(listed) == 1
    assert listed[0].session_id == session_id
    assert listed[0].message_count == 4