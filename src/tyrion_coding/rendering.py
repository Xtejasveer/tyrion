"""Simple terminal renderer for agent events (used by one-shot `tyrion "prompt"` runs)."""
from __future__ import annotations

from rich.console import Console
from rich.text import Text

from tyrion_agent.events import (
    AgentEvent,
    MessageEndEvent,
    MessageUpdateEvent,
    ToolExecutionEndEvent,
    ToolExecutionStartEvent,
)
from tyrion_agent.messages import AssistantMessage
from tyrion_coding import theme
from tyrion_coding.display import result_excerpt, shorten_home, tool_summary

class PrintRenderer:
    """Renders agent events to the terminal using rich."""
    def __init__(self) -> None:
        self.console = Console(theme=theme.RICH_THEME, highlight=False)
        self._streaming = False
        self._tool_name = ""

    def header(self, model: str, cwd: str, session_id: str) -> None:
        """Print the one-line banner shown before a run."""
        self.console.print(
            Text.assemble(
                ("◆ ", theme.GOLD),
                ("Tyrion", f"bold {theme.GOLD}"),
                ("  ", ""),
                (model, theme.MUTED),
                (" · ", theme.FAINT),
                (shorten_home(cwd), theme.MUTED),
                (" · ", theme.FAINT),
                (session_id[:8], theme.FAINT),
            )
        )

    def handle_event(self, event:AgentEvent) -> None:
        """Process one agent event and print it"""
        if isinstance(event, MessageUpdateEvent):
            if isinstance(event.message, AssistantMessage):
                from tyrion_agent.provider_events import TextDeltaEvent

                if isinstance(event.assistant_message_event, TextDeltaEvent):
                    if not self._streaming:
                        self._streaming = True
                        self.console.print()
                    # Text(...) so a reply containing "[...]" is not read as markup.
                    self.console.print(
                        Text(event.assistant_message_event.delta), end="", soft_wrap=True
                    )
        elif isinstance(event, MessageEndEvent):
            if isinstance(event.message, AssistantMessage) and getattr(event.message, "stop_reason", None) == "error":
                self.console.print(
                    Text.assemble(
                        ("✕ ", f"bold {theme.RED}"),
                        (event.message.error_message or "Unknown error", theme.RED),
                    )
                )
            if isinstance(event.message, AssistantMessage) and self._streaming:
                self._streaming = False
                self.console.print()
        elif isinstance(event, ToolExecutionStartEvent):
            self._tool_name = event.tool_name
            line = Text.assemble(
                ("\n  ▸ ", theme.GOLD),
                (event.tool_name, "bold"),
            )
            summary = tool_summary(event.tool_name, event.args)
            if summary:
                line.append(f"  {summary}", style=theme.MUTED)
            self.console.print(line)
        elif isinstance(event, ToolExecutionEndEvent):
            lines, hidden = result_excerpt(event.tool_name, event.result.text, event.is_error)
            rail = theme.RED if event.is_error else theme.BORDER_STRONG
            body = "#d98b8f" if event.is_error else theme.MUTED
            for line in lines:
                self.console.print(
                    Text.assemble(("    │ ", rail), (line, body)), overflow="ellipsis", no_wrap=True
                )
            if hidden:
                self.console.print(
                    Text.assemble(("    │ ", rail), (f"… {hidden} more line{'s' if hidden != 1 else ''}", theme.FAINT))
                )
