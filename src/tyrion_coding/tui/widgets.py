from __future__ import annotations

import re
from typing import TYPE_CHECKING
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Label, Static, TextArea

from tyrion_coding.commands import SlashCommand, registry

if TYPE_CHECKING:
    from tyrion_agent.types import JSONValue

# The command list is open while the whole input is a single "/word" with no
# space yet. Once the user types a space they are entering arguments.
_COMMAND_PREFIX = re.compile(r"/\S*")


class CommandMenu(Widget):
    """List of slash commands shown above the prompt while the user types `/...`.

    It never takes focus. PromptInput keeps the keyboard and drives it through
    `show_for`, `move`, `hide` and `selected_command`.
    """

    DEFAULT_CSS = """
    CommandMenu {
        display: none;
        width: 100%;
        height: auto;
        margin-bottom: 1;
    }
    """

    MAX_ROWS = 8

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._matches: list[SlashCommand] = []
        self._selected = 0
        self._top = 0  # first visible row, when there are more than MAX_ROWS

    @property
    def matches(self) -> tuple[SlashCommand, ...]:
        return tuple(self._matches)

    @property
    def is_open(self) -> bool:
        return bool(self._matches)

    @property
    def selected_command(self) -> SlashCommand | None:
        return self._matches[self._selected] if self._matches else None

    def show_for(self, text: str) -> None:
        """Open (or refresh) the list for what is in the prompt, or close it."""
        matches = registry.matching(text) if _COMMAND_PREFIX.fullmatch(text) else []
        if not matches:
            self.hide()
            return
        if [cmd.name for cmd in matches] != [cmd.name for cmd in self._matches]:
            self._selected = 0  # a different set of commands: start at the top
            self._top = 0
        self._matches = matches
        self.display = True
        self.refresh(layout=True)

    def hide(self) -> None:
        self._matches = []
        self._selected = 0
        self._top = 0
        self.display = False

    def move(self, delta: int) -> None:
        """Move the highlight up (-1) or down (+1), wrapping around the ends."""
        if not self._matches:
            return
        self._selected = (self._selected + delta) % len(self._matches)
        if self._selected < self._top:
            self._top = self._selected
        elif self._selected >= self._top + self.MAX_ROWS:
            self._top = self._selected - self.MAX_ROWS + 1
        self.refresh()

    def render(self) -> Text:
        name_width = max((len(cmd.name) for cmd in self._matches), default=0)
        rows: list[Text] = []
        for index in range(self._top, min(self._top + self.MAX_ROWS, len(self._matches))):
            command = self._matches[index]
            selected = index == self._selected
            row = Text(no_wrap=True, overflow="ellipsis")
            row.append(
                f" {command.name.ljust(name_width)}  ",
                style="bold white on #2563eb" if selected else "bold #e5e5e5",
            )
            row.append(
                command.description,
                style="white on #2563eb" if selected else "#7a7a7a",
            )
            if selected:  # extend the highlight across the full row
                row.append(" " * max(0, self.size.width - row.cell_len), style="on #2563eb")
            rows.append(row)
        return Text("\n").join(rows)


class PromptInput(TextArea):
    """Multi-line prompt input with submit on Enter and Tab completion."""

    class Submitted(Message):
        """Event fired when user submits a prompt."""
        def __init__(self, text: str) -> None:
            super().__init__()
            self.text = text

    def __init__(self, menu: CommandMenu | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.show_line_numbers = False
        self.menu = menu

    def _handle_menu_key(self, event: events.Key, menu: CommandMenu) -> bool:
        """Let the open command list handle a key. Returns True if it did."""
        key = event.key
        if key in ("up", "down"):
            menu.move(-1 if key == "up" else 1)
        elif key == "escape":
            menu.hide()
        elif key == "enter":
            command = menu.selected_command
            if command is not None:
                self.post_message(self.Submitted(command.name))
            self.text = ""
        elif key == "tab":
            command = menu.selected_command
            if command is not None:
                # Fill the name in and leave room to type arguments.
                self.text = command.name + " "
                self.move_cursor((0, len(self.text)))
        else:
            return False
        # Stop the TextArea and the app (cursor movement, Escape = cancel run)
        # from also reacting to a key the list has used.
        event.stop()
        event.prevent_default()
        return True

    def on_key(self, event: events.Key) -> None:
        """Handle key presses inside the prompt input area."""
        if self.menu is not None and self.menu.is_open and self._handle_menu_key(event, self.menu):
            return

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


class PromptBox(Vertical):
    """Compound prompt box with input area and bottom model pill."""

    def __init__(self, model_name: str = "gpt-4.1-mini", **kwargs) -> None:
        super().__init__(**kwargs)
        self.model_name = model_name

    def compose(self) -> ComposeResult:
        menu = CommandMenu(id="command-menu")
        yield menu
        yield PromptInput(
            placeholder='Ask anything... "Fix a TODO in the codebase"',
            id="prompt-input",
            menu=menu,
        )
        yield Label(
            f"[bold #3b82f6]Build[/] [dim]·[/] [bold white]{self.model_name}[/] [dim]Tyrion[/]",
            id="prompt-model-pill",
        )

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        """Show the command list while the user is typing a `/command`."""
        self.query_one(CommandMenu).show_for(event.text_area.text)

    def set_model(self, model_name: str) -> None:
        """Update model name shown in the bottom pill."""
        self.model_name = model_name
        try:
            pill = self.query_one("#prompt-model-pill", Label)
            pill.update(
                f"[bold #3b82f6]Build[/] [dim]·[/] [bold white]{model_name}[/] [dim]Tyrion[/]"
            )
        except Exception:
            pass


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