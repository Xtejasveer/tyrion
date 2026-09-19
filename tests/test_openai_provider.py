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


def _provider_with_handler(handler) -> OpenAICompatibleProvider:
    provider = OpenAICompatibleProvider(
        OpenAICompatibleConfig(api_key="test-key", base_url="http://test")
    )
    provider._client = httpx.AsyncClient(
        base_url="http://test", transport=httpx.MockTransport(handler)
    )
    return provider


def _provider(body: bytes, requests: list | None = None) -> OpenAICompatibleProvider:
    def handler(request: httpx.Request) -> httpx.Response:
        if requests is not None:
            requests.append(request)
        return httpx.Response(200, content=body)

    return _provider_with_handler(handler)


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


# --- real token usage --------------------------------------------------------

USAGE = {
    "prompt_tokens": 1234,
    "completion_tokens": 56,
    "total_tokens": 1290,
    "prompt_tokens_details": {"cached_tokens": 1000},  # nested: not kept
}


@pytest.mark.asyncio
async def test_request_asks_the_server_to_report_usage() -> None:
    requests: list = []
    provider = _provider(_sse(_chunk({"content": "hi"}, "stop")), requests)

    await _collect(provider)

    assert json.loads(requests[0].content)["stream_options"] == {"include_usage": True}


@pytest.mark.asyncio
async def test_usage_from_the_trailing_chunk_is_stored_on_the_message() -> None:
    # The usage chunk comes AFTER the finish_reason chunk and has no choices.
    provider = _provider(
        _sse(
            _chunk({"content": "hi"}),
            _chunk({}, "stop"),
            {"choices": [], "usage": USAGE},
        )
    )

    events = await _collect(provider)

    done = events[-1]
    assert isinstance(done, AssistantDoneEvent)
    assert done.message.text == "hi"
    assert done.message.usage == {
        "prompt_tokens": 1234,
        "completion_tokens": 56,
        "total_tokens": 1290,
    }


@pytest.mark.asyncio
async def test_usage_is_read_for_tool_call_replies_too() -> None:
    provider = _provider(
        _sse(
            _chunk(
                {
                    "tool_calls": [
                        {"index": 0, "id": "c1", "function": {"name": "read", "arguments": "{}"}}
                    ]
                }
            ),
            _chunk({}, "tool_calls"),
            {"choices": [], "usage": USAGE},
        )
    )

    events = await _collect(provider)

    done = events[-1]
    assert done.message.stop_reason == "toolUse"
    assert done.message.usage["prompt_tokens"] == 1234


@pytest.mark.asyncio
async def test_missing_usage_leaves_it_empty() -> None:
    provider = _provider(_sse(_chunk({"content": "hi"}, "stop")))

    events = await _collect(provider)

    assert events[-1].message.usage == {}


@pytest.mark.asyncio
async def test_server_that_rejects_stream_options_is_retried_without_it() -> None:
    requests: list = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        if "stream_options" in requests[-1]:
            return httpx.Response(
                400, json={"error": {"message": "Unrecognized request argument: stream_options"}}
            )
        return httpx.Response(200, content=_sse(_chunk({"content": "hi"}, "stop")))

    provider = _provider_with_handler(handler)

    events = await _collect(provider)

    assert isinstance(events[-1], AssistantDoneEvent)
    assert events[-1].message.text == "hi"
    assert len(requests) == 2
    assert "stream_options" not in requests[1]

    # It remembers, so later requests do not fail first.
    await _collect(provider)
    assert len(requests) == 3
    assert "stream_options" not in requests[2]


@pytest.mark.asyncio
async def test_an_unrelated_400_is_reported_not_retried() -> None:
    requests: list = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(400, json={"error": {"message": "invalid model"}})

    events = await _collect(_provider_with_handler(handler))

    assert len(requests) == 1
    assert isinstance(events[-1], AssistantErrorEvent)
    assert "invalid model" in (events[-1].error.error_message or "")


@pytest.mark.asyncio
async def test_cancelling_after_the_model_finished_does_not_discard_the_reply() -> None:
    # Once finish_reason has arrived we are only waiting for the usage chunk, so
    # a late cancel must not turn a complete reply into an aborted one.
    token = SimpleCancellationToken()
    provider = _provider(
        _sse(
            _chunk({"content": "done"}, "stop"),  # text and finish in one chunk
            {"choices": [], "usage": USAGE},
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
            token.cancel()  # the model has already finished at this point

    assert isinstance(events[-1], AssistantDoneEvent)
    assert events[-1].message.text == "done"
    assert events[-1].message.usage["prompt_tokens"] == 1234


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
