"""Context window token accounting and heuristics."""

from __future__ import annotations
import json 

from tyrion_agent.messages import (
    AgentMessage,
    AssistantMessage,
    ToolResultMessage,
    UserMessage
)

def estimate_tokens(text: str) -> int:
    """Estimate token count based on charachter length (1 token ~= 4 chars.)"""
    if not text:
        return 0
    return max(1, len(text) // 4)

def estimate_message_tokens(message: AgentMessage) -> int:
    """Calculate token count of individual user, assistant or tool message."""
    tokens = 0
    if isinstance(message, UserMessage):
        tokens += estimate_tokens(message.content)
    elif isinstance(message, AssistantMessage):
        tokens += estimate_tokens(message.text)
        for tc in message.tool_calls:
            tokens += estimate_tokens(tc.name)
            tokens += estimate_tokens(json.dumps(tc.arguments))
    elif isinstance(message, ToolResultMessage):
        tokens += estimate_tokens(message.text)
    return tokens

def estimate_session_tokens(
        system_prompt: str, messages: list[AgentMessage]
) -> int:
    """Calculate total token count of system instructions and all messages."""
    total = estimate_tokens(system_prompt)
    for msg in messages:
        total += estimate_message_tokens(msg)
    return total