"""Token accounting: tool schemas, and anchoring on real API usage."""

from __future__ import annotations

from pathlib import Path

import pytest

from tyrion_agent.messages import AssistantMessage, UserMessage
from tyrion_agent.provider_events import AssistantDoneEvent
from tyrion_ai.fake import FakeProvider
from tyrion_coding.context_window import (
    estimate_context_tokens,
    estimate_session_tokens,
    estimate_tokens,
    estimate_tools_tokens,
)
from tyrion_coding.session import CodingSession
from tyrion_coding.session_coding import SessionManager
from tyrion_coding.tools import create_coding_tools


def _reply(text: str = "ok", **usage: int) -> AssistantMessage:
    return AssistantMessage(content=text, model="m", usage=dict(usage))


def _real_usage(prompt: int, completion: int) -> dict[str, int]:
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": prompt + completion,
    }


# --- tool definitions --------------------------------------------------------


def test_tool_definitions_are_counted(tmp_path: Path) -> None:
    tools = create_coding_tools(tmp_path)

    assert estimate_tools_tokens([]) == 0
    assert estimate_tools_tokens(tools) > 100  # the four schemas are not free

    without = estimate_session_tokens("system", [UserMessage(content="hi")])
    with_tools = estimate_session_tokens("system", [UserMessage(content="hi")], tools)
    assert with_tools == without + estimate_tools_tokens(tools)


# --- anchoring on real usage -------------------------------------------------


def test_without_real_usage_everything_is_estimated() -> None:
    messages = [UserMessage(content="x" * 400), _reply("y" * 400)]

    assert estimate_context_tokens("system", messages) == estimate_session_tokens(
        "system", messages
    )


def test_real_usage_replaces_the_estimate_for_everything_before_it() -> None:
    messages = [
        UserMessage(content="x" * 40_000),  # would be estimated at 10,000 tokens
        AssistantMessage(content="ok", model="m", usage=_real_usage(prompt=1_000, completion=50)),
        UserMessage(content="z" * 400),  # new since the reply: estimated at 100
    ]

    assert estimate_context_tokens("s" * 40_000, messages) == 1_000 + 50 + 100


def test_the_latest_reply_with_usage_is_the_anchor() -> None:
    messages = [
        UserMessage(content="one"),
        AssistantMessage(content="a", model="m", usage=_real_usage(100, 10)),
        UserMessage(content="two"),
        AssistantMessage(content="b", model="m", usage=_real_usage(500, 20)),
        UserMessage(content="w" * 80),
    ]

    assert estimate_context_tokens("s", messages) == 500 + 20 + estimate_tokens("w" * 80)


def test_a_reply_without_usage_does_not_hide_an_earlier_anchor() -> None:
    aborted = AssistantMessage(content=[], model="m", stop_reason="aborted")
    messages = [
        UserMessage(content="one"),
        AssistantMessage(content="a", model="m", usage=_real_usage(100, 10)),
        UserMessage(content="two"),
        aborted,
    ]

    assert estimate_context_tokens("s", messages) == 100 + 10 + estimate_tokens("two")


def test_zero_usage_from_a_server_is_ignored() -> None:
    # Some local servers report 0 for everything: treat that as "no data".
    messages = [
        UserMessage(content="x" * 400),
        AssistantMessage(content="y" * 400, model="m", usage=_real_usage(0, 0)),
    ]

    assert estimate_context_tokens("system", messages) == estimate_session_tokens(
        "system", messages
    )


# --- through CodingSession ---------------------------------------------------


@pytest.mark.asyncio
async def test_session_uses_real_usage_to_decide_when_to_compact(tmp_path: Path) -> None:
    # A tiny conversation whose reply reports 110,000 prompt tokens: the text
    # estimate alone would never say "compact", but the real count does
    # (110,100 is over 80% of gpt-4o's 128,000 window).
    reply = AssistantMessage(content="hello", model="gpt-4o", usage=_real_usage(110_000, 100))
    manager = SessionManager(root=tmp_path)
    session_id, storage = manager.new_storage()
    session = CodingSession(
        cwd=tmp_path,
        provider=FakeProvider([[AssistantDoneEvent(message=reply)]]),
        model="gpt-4o",
        system="test",
        storage=storage,
        session_id=session_id,
        tools=[],
    )
    assert not session.needs_compaction()

    async for _event in session.prompt("hi"):
        pass

    assert session.context_limit() == 128_000
    assert session.context_tokens() == 110_100
    assert session.needs_compaction()
