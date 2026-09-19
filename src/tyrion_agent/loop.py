"""the pure agent loop - the engine that drives model <-> tool interaction."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping, Sequence

from tyrion_agent.events import (
    AgentEndEvent,
    AgentEvent,
    AgentStartEvent,
    MessageEndEvent,
    MessageStartEvent,
    MessageUpdateEvent,
    ToolExecutionEndEvent,
    ToolExecutionStartEvent,
    TurnEndEvent,
    TurnStartEvent,
)
from tyrion_agent.messages import (
    AgentMessage,
    AssistantMessage,
    TextContent,
    ToolCall,
    ToolResultMessage,
)
from tyrion_agent.provider import CancellationToken, ModelProvider
from tyrion_agent.provider_events import (
    AssistantErrorEvent,
    AssistantMessageEvent,
    AssistantStartEvent,
    AssistantDoneEvent
)
from tyrion_agent.tool_history import repair_tool_history
from tyrion_agent.tools import AgentTool, AgentToolResult

async def run_agent_loop(
        *,
        provider: ModelProvider,
        model: str,
        system: str,
        messages :list[AgentMessage],
        tools : list[AgentTool],
        prompts: Sequence[AgentMessage] =(),
        max_turns: int | None = None,
        signal: CancellationToken | None = None,
) -> AsyncIterator[AgentEvent]:
    """Run the provider/tool loop and emit the agent events.
    Args:
        provider: The model provider to stream responses from.
        model: Model name to use.
        system: System prompt text.
        messages: The mutable transcript. The loop APPENDS to this list.
        tools: Available tools the model can call.
        prompts: Initial messages to append (e.g. a new user message).
        max_turns: Optional safety cap on model turns.
        signal: Optional cancellation token.
    """
    new_messages: list[AgentMessage] = list(prompts)
    if prompts:
        messages.extend(prompts)

    tool_by_name = {tool.name: tool for tool in tools}
    turn =1

    ## Emit start events
    yield AgentStartEvent()
    yield TurnStartEvent()

    # Emit events for initial prompts messages
    for prompt in prompts:
        yield MessageStartEvent(message = prompt)
        yield MessageEndEvent(message = prompt)

    #Validate max_turns
    if max_turns is not None and max_turns < 1:
        error = _error_message(model, "max turns must be atleat 1")
        messages.append(error)
        new_messages.append(error)
        yield MessageStartEvent(message=error)
        yield MessageEndEvent(message=error)
        yield TurnEndEvent(message=error)
        yield AgentEndEvent(messages=new_messages)
        return

    ## --- Main Loop ---
    while True:
        # check max turns
        if max_turns is not None and turn > max_turns:
            error = _error_message(model, f"Reached the max turns limit ({max_turns})")
            messages.append(error)
            new_messages.append(error)
            yield MessageStartEvent(message=error)
            yield MessageEndEvent(message=error)
            yield TurnEndEvent(message=error)
            yield AgentEndEvent(messages=new_messages)
            return
        assistant : AssistantMessage | None = None

        async for event in _stream_assistant(
            provider = provider,
            model = model,
            system = system,
            messages = messages,
            tools =tools,
            signal= signal,
        ):
            yield event
            # capture the final assistant message

            if isinstance(event, MessageEndEvent) and isinstance(event.message, AssistantMessage):
                assistant = event.message

        # The provider should always produce a message, but incase it doesn't
        if assistant is None:
            assistant = _error_message(model, "Provider produced no assistant message")
            yield MessageStartEvent(message=assistant)
            yield MessageEndEvent(message=assistant)

        ## Add assistant message to transcript
        messages.append(assistant)
        new_messages.append(assistant)

        if assistant.stop_reason in {"error", "aborted"}:
            yield TurnEndEvent(message=assistant)
            yield AgentEndEvent(messages=new_messages)
            return
        ## Execute tool calls (if any)
        calls = list(assistant.tool_calls)
        tool_results: list[ToolResultMessage] =[]

        for call in calls:
            async for event in _execute_tool_call(call, tool_by_name, signal):
                yield event

                if isinstance(event, MessageEndEvent) and isinstance(event.message, ToolResultMessage):
                    tool_results.append(event.message)
                    messages.append(event.message)
                    new_messages.append(event.message)

        # Emit turn end
        yield TurnEndEvent(message = assistant, tool_results=tool_results)
        turn +=1

        if not calls:
            break

        # Cancelled while tools were running: stop here instead of asking the
        # model for another turn.
        if signal is not None and signal.is_cancelled():
            yield AgentEndEvent(messages=new_messages)
            return
        yield TurnStartEvent()
    yield AgentEndEvent(messages=new_messages)


### Stream assistant response from porvider

async def _stream_assistant(
        *,
        provider:  ModelProvider,
        model: str,
        system : str,
        messages: list[AgentMessage],
        tools: list[AgentTool],
        signal: CancellationToken | None = None,
) -> AsyncIterator[AgentEvent]:
    """Strema one model's response and convert provider events to agent events."""

    clean = repair_tool_history(messages)
    clean_messages = list(clean.messages)

    source : AsyncIterator[AssistantMessageEvent] = provider.stream_response(
        model = model,
        system = system,
        messages = clean.messages,
        tools=tools,
        signal = signal,
    )
    started = False
    async for event in source:
        if isinstance(event,AssistantStartEvent):
            started = True
            yield MessageStartEvent(message = event.partial)

        elif isinstance(event, AssistantDoneEvent):
            if not started:
                yield MessageStartEvent(message = event.message)
            yield MessageEndEvent(message = event.message)

        elif isinstance(event, AssistantErrorEvent):
            if not started:
                yield MessageStartEvent(message=event.error)
            yield MessageEndEvent(message=event.error)
        else :
            yield MessageUpdateEvent(
                message = event.partial,
                assistant_message_event=event,
            )

async def _execute_tool_call(
        call: ToolCall,
        tools: Mapping[str, AgentTool],
        signal: CancellationToken | None,
) -> AsyncIterator[AgentEvent]:
    """Execute one tool call and emit events."""

    # Announce the tool execution
    yield ToolExecutionStartEvent(
        tool_call_id = call.id,
        tool_name = call.name,
        args = call.arguments,
    )

    #check if cancelled
    if signal is not None and signal.is_cancelled():
        result = _error_result("Operation aborted")
        is_error= True

    else:
        ## Find the tool
        tool = tools.get(call.name)
        if tool is None:
            result = _error_result(f"Unknown Tool: {call.name}")
            is_error = True
        else:
            result, is_error = await _run_tool(tool, call, signal)

    ## Announce the result
    yield ToolExecutionEndEvent(
        tool_call_id = call.id,
        tool_name = call.name,
        result = result,
        is_error = is_error
    )

    # Emit tool result message
    message = ToolResultMessage(
        tool_call_id=call.id,
        tool_name=call.name,
        content=result.content,
        is_error=is_error,
    )
    yield MessageStartEvent(message=message)
    yield MessageEndEvent(message=message)

async def _run_tool(
        tool: AgentTool,
        call: ToolCall,
        signal: CancellationToken | None,
) -> tuple[AgentToolResult, bool]:
    """Run a tool catching any exceptions"""
    try: 
        result = await tool.execute(call.id, call.arguments, signal)
        return result, False
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        return _error_result(str(exc)), True

## Helpers
def _error_result(message: str) -> AgentToolResult:
    """Create an error tool result."""
    return AgentToolResult(content=[TextContent(text=message)])


def _error_message(model: str, message: str) -> AssistantMessage:
    """Create an error assistant message."""
    return AssistantMessage(
        model=model,
        content=[],
        stop_reason="error",
        error_message=message,
    )