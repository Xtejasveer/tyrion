"""Ensure tool calls/ tool result consistency in transcripts."""

from __future__ import annotations

from dataclasses import dataclass

from tyrion_agent.messages import (
    AgentMessage,
    AssistantMessage,
    TextContent,
    ToolResultMessage
)

@dataclass(frozen=True, slots=True)
class RepairedHistory:
    """A transcript with any orphaned tool calls patched."""

    messages: tuple[AgentMessage, ...]
    repairs: int

def repair_tool_history(
        messages: tuple[AgentMessage, ...] | list[AgentMessage],
) -> RepairedHistory:
    """Ensure every tool call has a matching tool result.

    Some providers (OpenAI, Anthropic) reject a conversation where an
    assistant message contains a tool call but no corresponding tool
    result message follows. This happens when a run is interrupted
    mid-tool-execution.

    This function appends synthetic error results for any orphaned
    tool calls so the provider gets a valid transcript.
    """
    result: list[AgentMessage] = list(messages)

    returned_ids: set[str] = {
        msg.tool_call_id
        for msg in messages
        if isinstance(msg, ToolResultMessage)
    }

    repairs = 0
    for msg in messages:
        if not isinstance(msg, AssistantMessage):
            continue

        for call in msg.tool_calls:
            if call.id not in returned_ids:
                result.append(
                    ToolResultMessage(
                        tool_call_id=call.id,
                        tool_name = call.name,
                        content = [TextContent(text = "tool call interrupted")],
                        is_error = True,
                    )
                )
                returned_ids.add(call.id)
                repairs += 1
    return RepairedHistory(messages = tuple(result), repairs = repairs)
