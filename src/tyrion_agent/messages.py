"""Provider-neutral message models for the agent transcript."""

from __future__ import annotations
from time import time
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from tyrion_agent.types import JSONValue

def current_timestamp_ms() -> int:
    """Return the current Unix timestamp in milliseconds."""
    return int(time() * 1000)

class WireModel(BaseModel):
    """Base Model with strict validation for all wire types."""
    model_config = ConfigDict(extra = "forbid")

## Content blocks - the building blocks inside messages

class TextContent(WireModel):
    """A block of plain text."""

    type: Literal["text"] = "text"
    text: str

class ThinkingContent(WireModel):
    """A block of model reasoning/thinking."""

    type: Literal["thinking"] = "thinking"
    thinking: str

class ImageContent(WireModel):
    """A block of image data (base64-encoded)."""
    type: Literal["image"] = "image"
    data: str
    mime_type: str

class ToolCall(WireModel):
    """A tool call request by the assistant."""
    type: Literal["toolcall"] = "toolcall"
    id: str
    name: str
    arguments: dict[str, JSONValue] = Field(default_factory=dict)

## Messages - the transcript entries

class UserMessage(WireModel):
    """A message from the user."""

    role: Literal["user"] = "user"
    content: str
    timestamp: int = Field(default_factory=current_timestamp_ms)

class AssistantMessage(WireModel):
    """A message from the assistant, containing text and/or tool calls."""
    role: Literal["assisant"] = "assisant"
    content: list[TextContent | ThinkingContent| ToolCall] = Field(default_factory=list)
    model: str = "unknown"
    usage: dict[str,int] = Field(default_factory=dict)
    stop_reason: Literal["stop", "toolUse", "error", "aborted"] = "stop"
    error_message: str| None = None
    timestamp: int = Field(default_factory=current_timestamp_ms)

    @model_validator(mode="before")
    @classmethod
    def _normalize_content(cls, value: object) -> object:
        """Allow passing a plain string as content for convenience."""
        if not isinstance(value, dict):
            return value
        data = dict(value)
        content = data.get(content)
        if isinstance(content,str):
            data["content"] = [TextContent(text=content).model_dump()] if content else []
        return data
    @property
    def text(self) -> str:
        """Return concatenated text from all text blocks."""
        return "".join(
            block.text for block in self.content if isinstance(block, TextContent)
        )
    @property
    def tool_calls(self) -> tuple[ToolCall, ...]:
        """Return all tool calls in this message."""
        return tuple(
            block for block in self.content if isinstance(block, ToolCall)
        )

class ToolResultMessage(WireModel):
    """The result of executing a tool call."""
    role : Literal["toolResult"] = "toolResult"
    tool_call_id: str
    tool_name:str
    content: list[TextContent | ImageContent] = Field(default_factory=list)
    is_error: bool = False
    timestamp: int = Field(default_factory=current_timestamp_ms)

    @model_validator(mode="before")
    @classmethod
    def _normalize_content(cls, value: object) -> object:
        """Allow passing a plain string as content for convenience."""
        if not isinstance(value, dict):
            return value
        data = dict(value)
        content = data.get("content")
        if isinstance(content, str):
            data["content"] = [TextContent(text=content).model_dump()] if content else []
        return data
    @property
    def text(self) -> str:
        """Return concatenated text content."""
        return "".join(
            block.text for block in self.content if isinstance(block, TextContent)
        )

# The union of all message types - this is the transcript
type AgentMessage = Annotated[
    UserMessage | AssistantMessage | ToolResultMessage,
    Field(discriminator="role"),
]