"""Context window token accounting and heuristics."""

from __future__ import annotations
import json
from collections.abc import Sequence

from tyrion_agent.messages import (
    AgentMessage,
    AssistantMessage,
    ToolResultMessage,
    UserMessage
)
from tyrion_agent.tools import AgentTool
from tyrion_ai.model_limits import DEFAULT_LIMITS, is_known_model

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

def estimate_tools_tokens(tools: Sequence[AgentTool]) -> int:
    """Estimate the tokens taken by tool definitions, which are sent with every request."""
    if not tools:
        return 0
    definitions = [
        {
            "name": tool.name,
            "description": tool.description,
            "parameters": dict(tool.parameters),
        }
        for tool in tools
    ]
    return estimate_tokens(json.dumps(definitions))

def estimate_session_tokens(
        system_prompt: str,
        messages: list[AgentMessage],
        tools: Sequence[AgentTool] = (),
) -> int:
    """Estimate total token count of the system prompt, tool definitions and all messages."""
    total = estimate_tokens(system_prompt) + estimate_tools_tokens(tools)
    for msg in messages:
        total += estimate_message_tokens(msg)
    return total

def _last_measured_context(messages: Sequence[AgentMessage]) -> tuple[int, int] | None:
    """Find the latest assistant reply with real token usage from the API.

    Returns (index of that reply, tokens in context up to and including it).
    The API's prompt_tokens covers everything sent (system prompt, tool
    definitions, all earlier messages) and completion_tokens is the reply itself.
    """
    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        if not isinstance(message, AssistantMessage):
            continue
        prompt = message.usage.get("prompt_tokens", 0)
        completion = message.usage.get("completion_tokens", 0)
        if prompt > 0:
            return index, prompt + completion
    return None

def estimate_context_tokens(
        system_prompt: str,
        messages: list[AgentMessage],
        tools: Sequence[AgentTool] = (),
) -> int:
    """Best estimate of how many tokens the next request will take.

    Uses the API's real token count from the latest reply when there is one, and
    only estimates the messages added since. With no real count yet (a new
    session, or right after a compaction) everything is estimated.
    """
    measured = _last_measured_context(messages)
    if measured is None:
        return estimate_session_tokens(system_prompt, messages, tools)
    index, tokens = measured
    return tokens + sum(estimate_message_tokens(msg) for msg in messages[index + 1:])

def unknown_model_notice(model_name: str) -> str | None:
    """A warning to show when we have no limits for this model, else None."""
    if is_known_model(model_name):
        return None
    return (
        f"No context-window data for '{model_name}'; assuming "
        f"{DEFAULT_LIMITS.context_window:,} tokens, so the token count and "
        "auto-compaction may be off. Set the real size in ~/.tyrion/models.json, e.g. "
        f'{{"{model_name}": {{"context_window": 8192}}}} (restart to apply).'
    )
