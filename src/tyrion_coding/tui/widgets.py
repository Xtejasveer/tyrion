from __future__ import annotations

from typing import TYPE_CHECKING
from rich.markdown import Markdown
from rich.panel import Panel
from textual import events
from textual.message import Message
from textual.widgets import Static, TextArea

if TYPE_CHECKING:
    from tyrion_agent.types import JSONValue


class PromptInput(TextArea):
    """Multi-line prompt input with submit on Enter and Tab completion."""

    class Submitted(Message):
        """Event fired when user submits a prompt."""
        def __init__(self, text: str) -> None:
            super().__init__()
            self.text = text

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.show_line_numbers = False

    def on_key(self, event: events.Key) -> None:
        """Handle key presses inside the prompt input area."""
        if event.key == "enter":
            event.prevent_default()
            text = self.text.strip()
            if text:
                self.post_message(self.Submitted(text))
                self.text = ""
        elif event.key == "shift+enter":
            # Allow shift+enter to input a real newline character
            self.insert("\n")
            event.prevent_default()
        elif event.key == "tab":
            # Tab completion for commands
            text = self.text
            if text.startswith("/"):
                event.prevent_default()
                parts = text.split(maxsplit=1)
                cmd_prefix = parts[0]
                rest = parts[1] if len(parts) > 1 else ""

                from tyrion_coding.commands import registry
                all_cmd_names = [cmd.name for cmd in registry.commands]
                
                matches = [name for name in all_cmd_names if name.startswith(cmd_prefix)]
                if matches:
                    try:
                        idx = matches.index(cmd_prefix)
                        next_match = matches[(idx + 1) % len(matches)]
                    except ValueError:
                        next_match = matches[0]
                    
                    new_text = next_match
                    if rest:
                        new_text += " " + rest
                    self.text = new_text
                    self.move_cursor((0, len(new_text)))


class TUIStatusBar(Static):
    """Custom status bar displaying session info, model, and engine status."""

    def __init__(self, session_id: str, model: str, cwd: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.session_id = session_id
        self.model = model
        self.cwd = cwd
        self.status_text = "Idle"
        self.current_tokens = 0
        self.token_limit = 0
        self._update_status()

    def set_status(self, text: str) -> None:
        """Update the engine status."""
        self.status_text = text
        self._update_status()

    def set_tokens(self, current: int, limit: int) -> None:
        """Update the estimated token usage count and limit."""
        self.current_tokens = current
        self.token_limit = limit
        self._update_status()

    def _update_status(self) -> None:
        tokens_str = (
            f"{self.current_tokens / 1000:.1f}K / {self.token_limit / 1000:.1f}K"
            if self.token_limit
            else "N/A"
        )
        self.update(
            f"💻 [bold]Tyrion[/bold] | Session: [cyan]{self.session_id}[/cyan] | "
            f"Model: [green]{self.model}[/green] | Tokens: [magenta]{tokens_str}[/magenta] | "
            f"Cwd: [yellow]{self.cwd}[/yellow] | Status: {self.status_text}"
        )


class ThinkingIndicator(Static):
    """Shows that the model is generating response."""

    def __init__(self, **kwargs) -> None:
        super().__init__("🤖 [italic]Thinking...[/italic]", **kwargs)
        self.visible = False


class MessageWidget(Static):
    """Renders a single message (user or assistant) inside a panel."""

    def __init__(self, role: str, content: str = "", **kwargs) -> None:
        super().__init__(**kwargs)
        self.role = role
        self.content = content
        self.update_content(content)

    def update_content(self, content: str) -> None:
        """Update message contents and re-render."""
        self.content = content
        if self.role == "user":
            self.update(
                Panel(
                    Markdown(content),
                    title="[bold green]You[/bold green]",
                    border_style="green",
                )
            )
        elif self.role == "assistant":
            self.update(
                Panel(
                    Markdown(content),
                    title="[bold blue]Tyrion[/bold blue]",
                    border_style="blue",
                )
            )
        else:
            self.update(
                Panel(
                    Markdown(content),
                    title=f"[bold]{self.role.capitalize()}[/bold]",
                )
            )


class ToolCallWidget(Static):
    """Displays a tool call start and subsequent execution status/results."""

    def __init__(self, tool_name: str, args: dict[str, JSONValue], **kwargs) -> None:
        super().__init__(**kwargs)
        self.tool_name = tool_name
        self.args = args
        self.result_text = ""
        self.is_error = False
        self.finished = False
        self._update_display()

    def set_result(self, result_text: str, is_error: bool = False) -> None:
        """Sets the execution outcome of the tool call."""
        self.result_text = result_text
        self.is_error = is_error
        self.finished = True
        self._update_display()

    def _update_display(self) -> None:
        args_str = ", ".join(f"{k}={v!r}" for k, v in self.args.items())
        if len(args_str) > 80:
            args_str = args_str[:80] + "..."

        status = "⏳ Executing" if not self.finished else ("❌ Error" if self.is_error else "✅ Success")
        border_style = "cyan" if not self.finished else ("red" if self.is_error else "green")

        content = f"[bold]{self.tool_name}[/bold]({args_str})\n"
        if self.finished:
            res = self.result_text
            if len(res) > 500:
                res = res[:500] + "\n... (truncated)"
            content += f"\n[dim]Result:[/dim]\n{res}"
        else:
            content += "\n[dim]Executing background tool logic...[/dim]"

        self.update(
            Panel(
                content,
                title=f"🛠️ Tool Call - {status}",
                border_style=border_style,
                expand=False,
            )
        )