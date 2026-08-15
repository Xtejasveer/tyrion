"""Events streamed by model providers (the raw model output)."""

from __future__ import annotations

from typing import Annotated, Literal
from pydantic import Field

from tyrion_agent.messages import AssistantMessage, ToolCall, WireModel

class AssistantStartEvent(WireModel):
    """Model response has started streaming."""
    type: Literal["assistant_start"] = "assistant_start"
    partial: AssistantMessage

class TextDeltaEvent(WireModel):
    """A chunk of the text from the model."""

    type: Literal["text_delta"] = "text_delta"
    delta: str
    partial: AssistantMessage

class ThinkingDeltaEvent(WireModel):
    """A chunk of reasoning/thinking from the model."""
    type: Literal["thinking_delta"] = "thinking_delta"
    delta: str
    partial: AssistantMessage

class ToolCallStartEvent(WireModel):
    """A tool call has started streaming."""

    type: Literal["tool_call_start"] = "tool_call_start"
    tool_call : ToolCall
    partial: AssistantMessage

class ToolCallDeltaEvent(WireModel):
    """A chunk of tool call arguments from the model."""
    type: Literal["tool_call_delta"] = "tool_call_delta"
    delta: str
    tool_call: ToolCall
    partial: AssistantMessage

class ToolCallEndEvent(WireModel):
    """A tool call has finished streaming."""
    type: Literal["tool_call_end"] = "tool_call_end"
    tool_call: ToolCall
    partial: AssistantMessage

class AssistantDoneEvent(WireModel):
    """Model response is complete"""

    type: Literal["assistant_done"] = "assistant_done"
    message: AssistantMessage

class AssistantErrorEvent(WireModel):
    """Model response errored."""

    type: Literal["assistant_error"] = "assistant_error"
    error: AssistantMessage

type AssistantMessageEvent = Annotated[
    AssistantStartEvent
    | TextDeltaEvent
    | ThinkingDeltaEvent
    | ToolCallStartEvent
    | ToolCallDeltaEvent
    | ToolCallEndEvent
    | AssistantDoneEvent
    | AssistantErrorEvent,
    Field(discriminator="type"),
]
