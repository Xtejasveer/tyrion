"""Dterministic fake providr for tests. No API calls, no network."""
from __future__ import annotations

from collections.abc import AsyncIterator, Iterable

from tyrion_agent.messages import AgentMessage
from tyrion_agent.provider_events import AssistantMessageEvent
from tyrion_agent.tools import AgentTool

class FakeProvider:
    """A provider that replays predefined event streams.
    
    
    Usage:
        provider = FakeProvider([
            [AssistantStartEvent(...), TextDeltaEvent(...), AssistantDoneEvent(...)]
            [AssistantStartEvent(...), AssistantDoneEvent(...)]
        ])

        # First call to stream_response returns stream 1
        # Second call returns stream 2
    """

    def __init__(self, streams: Iterable[Iterable[AssistantMessageEvent]]) -> None:
        self.streams = [list(stream) for stream in streams]
        self.calls: list[tuple[str, str, list[AgentMessage], list[AgentTool]]] =[]

    def stream_response(
        self,
        *,
        model : str,
        system: str,
        messages: list[AgentMessage],
        tools: list[AgentTool],
        signal : object | None = None,
    ) -> AsyncIterator[AssistantMessageEvent]:
        # Record what was called.
        self.calls.append((model, system, list(messages), list(tools)))

        # Pop the next scripted stream

        stream = self.streams.pop(0) if self.streams else []

        async def iterator() -> AsyncIterator[AssistantMessageEvent]:
            for event in stream:
                yield event
                
        return iterator()

    