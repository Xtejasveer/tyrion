"""Agent loop: turn limit and cancellation."""

from __future__ import annotations

import pytest

from tyrion_agent.events import AgentEndEvent
from tyrion_agent.harness import SimpleCancellationToken
from tyrion_agent.loop import run_agent_loop
from tyrion_agent.messages import AssistantMessage, TextContent, ToolCall, UserMessage
from tyrion_agent.provider_events import AssistantDoneEvent
from tyrion_agent.tools import AgentTool, AgentToolResult
from tyrion_ai.fake import FakeProvider


def _tool_call_stream(call_id: str, name: str) -> list:
    message = AssistantMessage(
        content=[ToolCall(id=call_id, name=name, arguments={})],
        model="fake-model",
        stop_reason="toolUse",
    )
    return [AssistantDoneEvent(message=message)]


def _text_stream(text: str) -> list:
    return [AssistantDoneEvent(message=AssistantMessage(content=text, model="fake-model"))]


def _noop_tool(name: str = "noop", on_run=None) -> AgentTool:
    async def execute(tool_call_id, arguments, signal=None, on_update=None):
        if on_run is not None:
            on_run()
        return AgentToolResult(content=[TextContent(text="ok")])

    return AgentTool(
        name=name,
        description="does nothing",
        parameters={"type": "object", "properties": {}},
        execute_fn=execute,
    )


async def _run(provider, tools, **kwargs) -> tuple[list, list]:
    transcript: list = []
    events = [
        event
        async for event in run_agent_loop(
            provider=provider,
            model="fake-model",
            system="test",
            messages=transcript,
            tools=tools,
            prompts=[UserMessage(content="go")],
            **kwargs,
        )
    ]
    return events, transcript


@pytest.mark.asyncio
async def test_max_turns_limit_ends_the_run_cleanly() -> None:
    # Turn 1 calls a tool, so the loop wants a turn 2, which max_turns=1 forbids.
    provider = FakeProvider([_tool_call_stream("c1", "noop"), _text_stream("never reached")])

    events, transcript = await _run(provider, [_noop_tool()], max_turns=1)

    assert isinstance(events[-1], AgentEndEvent)
    last = transcript[-1]
    assert isinstance(last, AssistantMessage)
    assert last.stop_reason == "error"
    assert "max turns" in (last.error_message or "").lower()
    assert len(provider.calls) == 1


@pytest.mark.asyncio
async def test_max_turns_below_one_ends_the_run_cleanly() -> None:
    provider = FakeProvider([_text_stream("never reached")])

    events, transcript = await _run(provider, [], max_turns=0)

    assert isinstance(events[-1], AgentEndEvent)
    assert transcript[-1].stop_reason == "error"
    assert provider.calls == []


@pytest.mark.asyncio
async def test_cancel_during_a_tool_does_not_start_another_turn() -> None:
    token = SimpleCancellationToken()
    provider = FakeProvider(
        [_tool_call_stream("c1", "stop"), _text_stream("must not be requested")]
    )

    events, transcript = await _run(
        provider, [_noop_tool("stop", on_run=token.cancel)], signal=token
    )

    assert len(provider.calls) == 1  # the model was not asked for a second turn
    assert isinstance(events[-1], AgentEndEvent)
    assert [msg.role for msg in transcript] == ["user", "assistant", "toolResult"]
