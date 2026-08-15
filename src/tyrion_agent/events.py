"""Events emitted by the portable agent layer."""

from __future__ import annotations
from typing import Annotated, Literal

from pydantic import Field

from tyrion_agent.messages import AgentMessage, ToolResultMessage, WireModel
from tyrion_agent.provider_events import AssistantMessageEvent
from tyrion_agent.tools import AgentToolResult
from tyrion_agent.types import JSONValue

class AgentStartEvent(WireModel):
    """The agent has started processing."""
    type: Literal["agent_start"] = "agent_start"

class AgentEndEvent(WireModel):
    """The agent has finished processing."""

    type: Literal["agent_end"] = "agent_end"
    messages: list[AgentMessage] = Field(default_factory=list)

class TurnStartEvent(WireModel):
    """A new model turn has started."""

    type: Literal["turn_start"] = "turn_start"

class TurnEndEvent(WireModel):
    """A model turn has completed."""

    type: Literal["turn_end"] = "turn_end"
    message: AgentMessage
    tool_results: list[ToolResultMessage] = Field(default_factory=list)

class MessageStartEvent(WireModel):
    """A message has started (user, assistant or tool result)."""
    type: Literal["message_start"] = "message_start"
    message: AgentMessage

class MessageUpdateEvent(WireModel):
    """A streaming delta has arrived for the current message."""

    type: Literal["message_update"] = "message_update"
    message: AgentMessage
    assistant_message_event: AssistantMessageEvent

class MessageEndEvent(WireModel):
    """A message has been finalized."""
    type: Literal["message_end"] = "message_end"
    message: AgentMessage

class ToolExecutionStartEvent(WireModel):
    """A tool has started executing."""

    type: Literal["tool_execution_start"] = "tool_execution_start"
    tool_call_id: str
    tool_name : str
    args: dict[str, JSONValue] = Field(default_factory=dict)

class ToolExecutionUpdateEvent(WireModel):
    """A tool has started executing."""

    type: Literal["tool_execution_update"] = "tool_execution_update"
    tool_call_id: str
    tool_name : str
    args: dict[str, JSONValue] = Field(default_factory=dict)
    partial_result: AgentToolResult

class ToolExecutionEndEvent(WireModel):
    """A tool has finished executing."""
    type: Literal["tool_execution_end"] = "tool_execution_end"
    tool_call_id: str
    tool_name: str
    result: AgentToolResult
    is_error: bool
# Union of all agent events
type AgentEvent = Annotated[
    AgentStartEvent
    | AgentEndEvent
    | TurnStartEvent
    | TurnEndEvent
    | MessageStartEvent
    | MessageUpdateEvent
    | MessageEndEvent
    | ToolExecutionStartEvent
    | ToolExecutionUpdateEvent
    | ToolExecutionEndEvent,
    Field(discriminator="type"),
]