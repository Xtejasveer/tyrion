"""Simple terminal renderer for agent events."""
from __future__ import annotations

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax

from tyrion_agent.events import (
    AgentEvent,
    MessageEndEvent,
    MessageUpdateEvent,
    ToolExecutionEndEvent,
    ToolExecutionStartEvent,
)
from tyrion_agent.messages import AssistantMessage, ToolResultMessage

class PrintRenderer:
    """Renders agent events to the terminal using rich."""
    def __init__(self) -> None:
        self.console = Console()
        self._streaming = False

    def handle_event(self, event:AgentEvent) -> None:
        """Process one agent event and print it"""
        if isinstance(event, MessageUpdateEvent):
            if isinstance(event.message, AssistantMessage):
                from tyrion_agent.provider_events import TextDeltaEvent

                if isinstance(event.assistant_message_event, TextDeltaEvent):
                    if not self._streaming:
                        self._streaming = True
                        self.console.print()
                    self.console.print(
                        event.assistant_message_event.delta,
                        end = "",
                        highlight=False,
                    )
        elif isinstance(event, MessageEndEvent):
            if isinstance(event.message, AssistantMessage) and getattr(event.message, "stop_reason", None) == "error":
                self.console.print(Panel(event.message.error_message or "Unknown error", title="❌ API Error", border_style="red"))
            if isinstance(event.message, AssistantMessage) and self._streaming:
                self._streaming = False
                self.console.print()
                self.console.print()
        elif isinstance(event, ToolExecutionStartEvent):
            self.console.print(
                Panel(
                    f"[bold]{event.tool_name} [/bold]({_format_args(event.args)})",
                    title = "🛠️ Tool Call",
                    border_style= "cyan",
                    expand = False,
                )
            )
        elif isinstance(event, ToolExecutionEndEvent):
            # Show tool result (truncated)
            result_text = event.result.text
            if len(result_text) > 500:
                result_text = result_text[:500] + "\n... (truncated)"
            style = "red" if event.is_error else "green"
            title = "❌ Error" if event.is_error else "✅ Result"
            self.console.print(
                Panel(
                    result_text,
                    title=title,
                    border_style=style,
                    expand=False,
                )
            )
def _format_args(args: dict) -> str:
    """Format tool arguments for display."""
    if not args:
        return ""
    parts = []
    for key, value in args.items():
        if isinstance(value, str) and len(value) > 50:
            value = value[:50] + "..."
        parts.append(f"{key}={value!r}")
    return ", ".join(parts)
