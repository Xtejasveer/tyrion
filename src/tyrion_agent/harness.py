"""Stateful reusable agent brain built on top of the pure agent loop."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import suppress
from dataclasses import dataclass, field
from inspect import isawaitable
from typing import Literal

from tyrion_agent.events import AgentEvent, MessageEndEvent, MessageStartEvent
from tyrion_agent.loop import run_agent_loop
from tyrion_agent.messages import (
    AgentMessage,
    AssistantMessage,
    TextContent,
    ToolResultMessage,
    UserMessage,
)
from tyrion_agent.provider import ModelProvider
from tyrion_agent.tools import AgentTool

# A listener is any function that receives an event (sync or async)
EventListener = Callable[[AgentEvent], Awaitable[None] | None]


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class AgentHarnessConfig:
    """Everything the harness needs to run the loop."""

    provider: ModelProvider
    model: str
    system: str
    tools: list[AgentTool] = field(default_factory=list)
    max_turns: int | None = None


# ---------------------------------------------------------------------------
# Cancellation
# ---------------------------------------------------------------------------


class SimpleCancellationToken:
    """A simple flag that can be checked to see if work should stop."""

    def __init__(self) -> None:
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def is_cancelled(self) -> bool:
        return self._cancelled


# ---------------------------------------------------------------------------
# The Harness
# ---------------------------------------------------------------------------


class AgentHarness:
    """Reusable stateful agent brain.

    Owns the transcript, delegates to the pure agent loop,
    and provides a clean API for frontends.

    Usage:
        harness = AgentHarness(AgentHarnessConfig(
            provider=provider,
            model="gpt-4",
            system="You are a coding agent.",
            tools=[read_tool, bash_tool],
        ))

        async for event in harness.prompt("Read README.md"):
            print(event)
    """

    def __init__(
        self,
        config: AgentHarnessConfig,
        *,
        messages: Sequence[AgentMessage] = (),
    ) -> None:
        self._config = config
        self._messages: list[AgentMessage] = list(messages)
        self._listeners: list[EventListener] = []
        self._current_signal: SimpleCancellationToken | None = None
        self._running = False

    # --- Public properties ---

    @property
    def messages(self) -> tuple[AgentMessage, ...]:
        """Immutable snapshot of the current transcript."""
        return tuple(self._messages)

    @property
    def config(self) -> AgentHarnessConfig:
        return self._config

    @property
    def is_running(self) -> bool:
        return self._running

    # --- Core API ---

    def prompt(self, content: str) -> AsyncIterator[AgentEvent]:
        """Send a user message and run the agent loop.

        This is the main entry point. It:
        1. Appends a UserMessage to the transcript
        2. Runs the agent loop
        3. Yields events as they happen
        """
        return self.prompt_message(UserMessage(content=content))

    def prompt_message(self, message: AgentMessage) -> AsyncIterator[AgentEvent]:
        """Send an arbitrary message and run the agent loop."""
        self._ensure_not_running()
        self._running = True
        return self._run(prompts=(message,))

    def continue_(self) -> AsyncIterator[AgentEvent]:
        """Run the agent loop without appending a new message.

        Useful for:
        - Resuming after restoring a session
        - Continuing after an interrupted run
        """
        self._ensure_not_running()
        self._running = True
        return self._run()

    # --- Cancellation ---

    def cancel(self) -> None:
        """Cancel the current run.

        The loop will stop after the current tool finishes.
        Any unanswered tool calls get synthetic error results.
        """
        if self._current_signal is not None:
            self._current_signal.cancel()

    # --- Event listeners ---

    def subscribe(self, listener: EventListener) -> Callable[[], None]:
        """Subscribe to agent events. Returns an unsubscribe function.

        Listeners receive the same events as the prompt()/continue_()
        consumer. This lets persistence, logging, and other observers
        watch runs without being the main consumer.

        Usage:
            def on_event(event):
                print(f"Got: {event.type}")

            unsubscribe = harness.subscribe(on_event)
            # ... later ...
            unsubscribe()
        """
        self._listeners.append(listener)

        def unsubscribe() -> None:
            with suppress(ValueError):
                self._listeners.remove(listener)

        return unsubscribe

    # --- Transcript management ---

    def append_message(self, message: AgentMessage) -> None:
        """Manually append a message (used when restoring sessions)."""
        self._messages.append(message)

    def replace_messages(self, messages: Sequence[AgentMessage]) -> None:
        """Replace the entire transcript (used when restoring sessions)."""
        self._messages = list(messages)

    # --- Internal machinery ---

    async def _run(
        self,
        *,
        prompts: Sequence[AgentMessage] = (),
    ) -> AsyncIterator[AgentEvent]:
        """Run the agent loop and handle cleanup."""
        signal = SimpleCancellationToken()
        self._current_signal = signal

        try:
            # Repair any dangling tool calls from a previous interrupted run
            self._repair_interrupted_tools()

            # Run the loop
            async for event in run_agent_loop(
                provider=self._config.provider,
                model=self._config.model,
                system=self._config.system,
                messages=self._messages,
                prompts=prompts,
                tools=self._config.tools,
                max_turns=self._config.max_turns,
                signal=signal,
            ):
                # Notify all listeners
                await self._notify(event)
                # Yield to the consumer (CLI, TUI, etc.)
                yield event

        finally:
            # If we were cancelled, repair any new dangling tool calls
            if signal.is_cancelled():
                before = len(self._messages)
                self._repair_interrupted_tools()
                # Push repair messages to listeners so persistence sees them
                for message in self._messages[before:]:
                    with suppress(Exception):
                        await self._notify(MessageStartEvent(message=message))
                        await self._notify(MessageEndEvent(message=message))

            if self._current_signal is signal:
                self._current_signal = None
            self._running = False

    async def _notify(self, event: AgentEvent) -> None:
        """Send an event to all listeners."""
        for listener in list(self._listeners):
            result = listener(event)
            if isawaitable(result):
                await result

    def _ensure_not_running(self) -> None:
        """Prevent overlapping runs."""
        if self._running:
            raise RuntimeError(
                "AgentHarness is already running. "
                "Wait for the current run to finish before starting a new one."
            )

    def _repair_interrupted_tools(self) -> None:
        """Append synthetic error results for any unanswered tool calls.

        This happens when a run is cancelled mid-tool-execution.
        The model asked to call a tool, but we stopped before getting
        the result. We need to add a "Tool call interrupted" result
        so the transcript stays valid.
        """
        returned_ids: set[str] = {
            msg.tool_call_id
            for msg in self._messages
            if isinstance(msg, ToolResultMessage)
        }

        for msg in tuple(self._messages):
            if not isinstance(msg, AssistantMessage):
                continue
            for call in msg.tool_calls:
                if call.id not in returned_ids:
                    returned_ids.add(call.id)
                    self._messages.append(
                        ToolResultMessage(
                            tool_call_id=call.id,
                            tool_name=call.name,
                            content=[TextContent(text="Tool call interrupted by user")],
                            is_error=True,
                        )
                    )