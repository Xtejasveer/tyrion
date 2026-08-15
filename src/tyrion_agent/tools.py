"""Provider-neutral tool definitions and execution results."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Protocol

from pydantic import Field, model_validator

from tyrion_agent.messages import ImageContent, TextContent, ToolCall, WireModel
from tyrion_agent.types import JSONValue

class ToolCancellationToken(Protocol):
    """Protocol to check if tool execution should stop."""
    def is_cancelled(self) -> bool: ...

class AgentToolResult(WireModel):
    """Result produced by a tool execution."""

    content: list[TextContent | ImageContent] = Field(default_factory=list)
    details: JSONValue = None

    @model_validator(mode="before")
    @classmethod
    def _normalize_text_content(cls, value: object) -> object:
        """Allow passing a plain string as content."""
        if not isinstance(value, dict):
            return value
        data = dict(value)
        content = data.get("content")
        if isinstance(content, str):
            data["content"] = [TextContent(text = content).model_dump()] if content else []
        return data
    @property
    def text(self) -> str:
        return "".join(
            block.text for block in self.content if isinstance(block, TextContent)
        )

ToolUpdateCallback = Callable[[AgentToolResult], None]

## This is the clas that defines the protocol for a tool_executor 
class ToolExecutor(Protocol):
    """Protocol for the async function that excutes a tool."""
    def __call__(
            self,
            tool_call_id: str,
            arguments: Mapping[str, JSONValue],
            signal: ToolCancellationToken | None = None,
            on_update: ToolUpdateCallback | None = None,
    ) -> Awaitable[AgentToolResult]: ...

@dataclass(frozen= True, slots=True)
class AgentTool:
    """A tool that can be exposed to the model."""

    name: str
    description: str
    parameters: Mapping[str, JSONValue]
    execute_fn: ToolExecutor

    @property
    def input_schema(self) -> Mapping[str, JSONValue]:
        """Alias used by the provider payload builders."""
        return self.parameters
    async def execute(
            self,
            tool_call_id: str,
            arguments: Mapping[str, JSONValue],
            signal: ToolCancellationToken |None = None,
            on_update: ToolUpdateCallback | None = None,
    ) -> AgentToolResult:
        """Execute the tool"""
        return await self.execute_fn(tool_call_id, arguments, signal, on_update)

__all__ = [
    "AgentTool",
    "AgentToolResult",
    "ToolCall",
    "ToolCancellationToken",
    "ToolExecutor",
    "ToolUpdateCallback",
]