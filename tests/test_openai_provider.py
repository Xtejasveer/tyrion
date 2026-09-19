"""OpenAICompatibleProvider: SSE parsing and cancellation, using a mock HTTP server."""

from __future__ import annotations

import json

import httpx
import pytest

from tyrion_agent.harness import SimpleCancellationToken
from tyrion_agent.messages import AssistantMessage, UserMessage
from tyrion_agent.provider_events import (
    AssistantDoneEvent,
    AssistantErrorEvent,
    TextDeltaEvent,
)
from tyrion_ai.env import OpenAICompatibleConfig
from tyrion_ai.openai_compatible import OpenAICompatibleProvider


def _sse(*chunks: dict) -> bytes:
    body = "".join(f"data: {json.dumps(chunk)}\n\n" for chunk in chunks)
    return (body + "data: [DONE]\n\n").encode()


def _chunk(delta: dict, finish_reason: str | None = None) -> dict:
    return {"choices": [{"delta": delta, "finish_reason": finish_reason}]}


def _provider(body: bytes, requests: list | None = None) -> OpenAICompatibleProvider:
    def handler(request: httpx.Request) -> httpx.Response:
        if requests is not None:
            requests.append(request)
        return httpx.Response(200, content=body)

    provider = OpenAICompatibleProvider(
        OpenAICompatibleConfig(api_key="test-key", base_url="http://test")
    )
    provider._client = httpx.AsyncClient(
        base_url="http://test", transport=httpx.MockTransport(handler)
    )
    return provider


async def _collect(provider: OpenAICompatibleProvider, signal=None) -> list:
    return [
        event
        async for event in provider.stream_response(
            model="m",
            system="s",
            messages=[UserMessage(content="hi")],
            tools=[],
            signal=signal,
        )
    ]


# --- tool call arguments -----------------------------------------------------


@pytest.mark.asyncio
async def test_tool_call_arguments_sent_in_the_first_chunk_are_kept() -> None:
    # Some providers send the name AND the full arguments in a single chunk.
    provider = _provider(
        _sse(
            _chunk(
                {
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "c1",
                            "function": {"name": "read", "arguments": '{"path": "main.py"}'},
                        }
                    ]
                }
            ),
            _chunk({}, "tool_calls"),
        )
    )

    events = await _collect(provider)

    done = events[-1]
    assert isinstance(done, AssistantDoneEvent)
    assert done.message.stop_reason == "toolUse"
    assert done.message.tool_calls[0].name == "read"
    assert done.message.tool_calls[0].arguments == {"path": "main.py"}


@pytest.mark.asyncio
async def test_tool_call_arguments_split_across_chunks_still_work() -> None:
    # OpenAI's own style: name first with empty arguments, then argument fragments.
    def call(**function) -> dict:
        return _chunk({"tool_calls": [{"index": 0, **function}]})

    provider = _provider(
        _sse(
            call(id="c1", function={"name": "read", "arguments": ""}),
            call(function={"arguments": '{"path": '}),
            call(function={"arguments": '"main.py"}'}),
            _chunk({}, "tool_calls"),
        )
    )

    events = await _collect(provider)

    done = events[-1]
    assert isinstance(done, AssistantDoneEvent)
    assert done.message.tool_calls[0].arguments == {"path": "main.py"}


# --- empty response ----------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_response_is_reported_as_an_error_not_a_crash() -> None:
    provider = _provider(_sse(_chunk({}, "stop")))

    events = await _collect(provider)

    assert len(events) == 1
    assert isinstance(events[0], AssistantErrorEvent)
    assert events[0].error.stop_reason == "error"
    assert "empty response" in (events[0].error.error_message or "")


# --- cancellation ------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancelling_mid_stream_stops_reading_and_keeps_partial_text() -> None:
    token = SimpleCancellationToken()
    provider = _provider(
        _sse(
            _chunk({"content": "Hel"}),
            _chunk({"content": "lo"}),
            _chunk({"content": " world"}, "stop"),
        )
    )

    events = []
    async for event in provider.stream_response(
        model="m",
        system="s",
        messages=[UserMessage(content="hi")],
        tools=[],
        signal=token,
    ):
        events.append(event)
        if isinstance(event, TextDeltaEvent):
            token.cancel()  # the user hits Escape after the first bit of text

    last = events[-1]
    assert isinstance(last, AssistantErrorEvent)
    assert last.error.stop_reason == "aborted"
    assert last.error.text == "Hel"  # nothing after the cancel was consumed


@pytest.mark.asyncio
async def test_already_cancelled_run_makes_no_request() -> None:
    token = SimpleCancellationToken()
    token.cancel()
    requests: list = []
    provider = _provider(_sse(_chunk({"content": "hi"}, "stop")), requests)

    events = await _collect(provider, signal=token)

    assert requests == []
    assert len(events) == 1
    assert events[0].error.stop_reason == "aborted"


# --- replaying the transcript ------------------------------------------------


def test_payload_skips_assistant_messages_with_no_content() -> None:
    # An aborted or failed response is stored as an empty assistant message.
    # The API rejects those, so they must not be sent back.
    provider = _provider(b"")
    messages = [
        UserMessage(content="first"),
        AssistantMessage(content=[], model="m", stop_reason="aborted"),
        UserMessage(content="second"),
    ]

    payload = provider._build_payload("m", "system", messages, [])

    assert [msg["role"] for msg in payload["messages"]] == ["system", "user", "user"]
