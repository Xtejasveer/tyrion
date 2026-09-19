"""One-shot print mode: the compact output used by `tyrion "prompt"`."""

from __future__ import annotations

import io

from rich.console import Console

from tyrion_agent.events import (
    MessageEndEvent,
    MessageUpdateEvent,
    ToolExecutionEndEvent,
    ToolExecutionStartEvent,
)
from tyrion_agent.messages import AssistantMessage
from tyrion_agent.provider_events import TextDeltaEvent
from tyrion_agent.tools import AgentToolResult
from tyrion_coding.rendering import PrintRenderer


def _renderer() -> tuple[PrintRenderer, io.StringIO]:
    buffer = io.StringIO()
    renderer = PrintRenderer()
    renderer.console = Console(file=buffer, force_terminal=False, width=90, highlight=False)
    return renderer, buffer


def _say(renderer: PrintRenderer, *deltas: str) -> None:
    partial = AssistantMessage(content="x")
    for delta in deltas:
        renderer.handle_event(
            MessageUpdateEvent(
                message=partial,
                assistant_message_event=TextDeltaEvent(delta=delta, partial=partial),
            )
        )
    renderer.handle_event(MessageEndEvent(message=partial))


def test_the_banner_shows_model_folder_and_a_short_session_id(monkeypatch) -> None:
    monkeypatch.setenv("HOME", "/Users/someone")
    renderer, out = _renderer()

    renderer.header("gpt-4o", "/Users/someone/proj", "8fb9500034b047318c4118aa105e03e8")

    line = out.getvalue()
    assert "◆ Tyrion" in line
    assert "gpt-4o" in line and "~/proj" in line and "8fb95000" in line
    assert "8fb9500034b0" not in line


def test_streamed_text_is_printed_as_it_arrives() -> None:
    renderer, out = _renderer()

    _say(renderer, "Hello, ", "world")

    assert "Hello, world" in out.getvalue()


def test_text_that_looks_like_markup_is_printed_literally() -> None:
    # The old renderer parsed model output as Rich markup, so this used to crash.
    renderer, out = _renderer()

    _say(renderer, "closing tag [/bold] and [red]not red[/red]")

    assert "closing tag [/bold] and [red]not red[/red]" in out.getvalue()


def test_a_tool_call_is_one_line_followed_by_its_output() -> None:
    renderer, out = _renderer()

    renderer.handle_event(
        ToolExecutionStartEvent(tool_call_id="1", tool_name="bash", args={"command": "pytest -q"})
    )
    renderer.handle_event(
        ToolExecutionEndEvent(
            tool_call_id="1", tool_name="bash", is_error=False,
            result=AgentToolResult(content="3 passed\n"),
        )
    )  # fmt: skip

    text = out.getvalue()
    assert "▸ bash  pytest -q" in text
    assert "│ 3 passed" in text


def test_long_tool_output_is_cut_and_counted() -> None:
    renderer, out = _renderer()

    renderer.handle_event(
        ToolExecutionEndEvent(
            tool_call_id="1", tool_name="bash", is_error=True,
            result=AgentToolResult(content="\n".join(f"line {i}" for i in range(12))),
        )
    )  # fmt: skip

    text = out.getvalue()
    assert "line 7" in text and "line 8" not in text  # errors show 8 lines
    assert "… 4 more lines" in text


def test_a_successful_read_prints_a_line_count_not_the_file() -> None:
    renderer, out = _renderer()

    renderer.handle_event(
        ToolExecutionEndEvent(
            tool_call_id="1", tool_name="read", is_error=False,
            result=AgentToolResult(content="secret = 1\nother = 2\n"),
        )
    )  # fmt: skip

    text = out.getvalue()
    assert "2 lines" in text
    assert "secret" not in text


def test_an_api_error_is_reported_with_a_marker() -> None:
    renderer, out = _renderer()

    renderer.handle_event(
        MessageEndEvent(message=AssistantMessage(content=[], stop_reason="error", error_message="API error 429"))
    )

    assert "✕ API error 429" in out.getvalue()
