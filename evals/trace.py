"""Capture a Tyrion run as a strcutured, order-preserving trace.

This is a plain consumer of the agent event stream - no couplung to the loop
or harness internals, so it is unit-testable with synthetic events."""

from __future__ import annotations

from dataclasses import dataclass, field

from tyrion_agent.events import (
    AgentEvent,
    MessageEndEvent,
    ToolExecutionStartEvent,
    ToolExecutionEndEvent,
    TurnStartEvent
)
from tyrion_agent.messages import AssistantMessage

@dataclass
class ToolInvocation:
    """One tool call the agent made, with its result."""

    id: str
    name: str
    arguments: dict
    result_text: str = ""
    is_error: bool = False

@dataclass
class AgentTrace:
    """The full ordered record of one agent run."""

    task_input: str
    tool_calls: list[ToolInvocation] = field(default_factory=list)
    assistant_messages: list[str] = field(default_factory=list)
    turn_count: int = 0

    @property
    def final_output(self) -> str:
        """The agent's closing message (best proxy for its answer)"""
        return self.assistant_messages[-1] if self.assistant_messages else ""

class TraceCollector:
    """Feed it agent events with observe(); call build() when the run ends."""

    def __init__(self, task_input: str) -> None:
        self._trace = AgentTrace(task_input=task_input)
        self._by_id: dict[str, ToolInvocation] = {}

    def observe(self, event:AgentEvent) -> None:
        if isinstance(event, ToolExecutionStartEvent):
            invocation = ToolInvocation(
                id = event.tool_call_id,
                name = event.tool_name,
                arguments = dict(event.args),
            )
            self._by_id[event.tool_call_id] = invocation
            self._trace.tool_calls.append(invocation)
        elif isinstance(event, ToolExecutionEndEvent):
            invocation = self._by_id.get(event.tool_call_id)
            if invocation is not None:
                invocation.result_text = event.result.text
                invocation.is_error = event.is_error
        elif isinstance(event, TurnStartEvent):
            self._trace.turn_count +=1
        elif isinstance(event, MessageEndEvent) and isinstance(event.message, AssistantMessage):
            text = event.message.text.strip()
            if text:
                self._trace.assistant_messages.append(text)

    def build(self) -> AgentTrace:
        return self._trace