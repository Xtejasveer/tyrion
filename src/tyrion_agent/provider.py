"""Provider contract owned by Tyrion's portable agent layer."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from tyrion_agent.messages import AgentMessage
from tyrion_agent.provider_events import AssistantMessageEvent
from tyrion_agent.tools import AgentTool

class CancellationToken(Protocol):
    """Check whether the current stream should stop."""

    def is_cancelled(self) -> bool : ...

class ModelProvider(Protocol):
    """Provider-neutral model streaminig interface.
    Every LLM adapter (OpenAI, Anthropic, Fake) implements this method.
    """

    def stream_response(
            self,
            *,
            model: str,
            system: str,
            messages: list[AgentMessage],
            tools: list[AgentTool],
            signal: CancellationToken | None = None,
    ) -> AsyncIterator[AssistantMessageEvent]:
        """Stream one model response as assistant message events."""
        ...
