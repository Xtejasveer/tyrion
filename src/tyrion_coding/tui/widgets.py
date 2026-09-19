from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING

from rich.console import Group, RenderableType
from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.timer import Timer
from textual.widget import Widget
from textual.widgets import Label, Static, TextArea

from tyrion_coding import theme
from tyrion_coding.commands import SlashCommand, registry
from tyrion_coding.display import (
    format_tokens,
    result_excerpt,
    shorten_home,
    token_bar,
    tool_summary,
    truncate_left,
    usage_color,
)

if TYPE_CHECKING:
    from tyrion_agent.types import JSONValue

SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

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
        padding-bottom: 1;
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
            if selected:
                row.append(" ▌ ", style=f"bold {theme.GOLD} on {theme.GOLD_TINT}")
                row.append(command.name.ljust(name_width), style=f"bold {theme.GOLD} on {theme.GOLD_TINT}")
                row.append("  " + command.description, style=f"{theme.TEXT} on {theme.GOLD_TINT}")
                # extend the highlight across the full row
                row.append(" " * max(0, self.size.width - row.cell_len), style=f"on {theme.GOLD_TINT}")
            else:
                row.append("   ")
                row.append(command.name.ljust(name_width), style=theme.TEXT)
                row.append("  " + command.description, style=theme.MUTED)
            rows.append(row)
        rows.append(
            Text("   ↑↓ navigate   ↵ run   tab complete   esc close", style=theme.FAINT, no_wrap=True)
        )
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


def _model_label(model_name: str) -> Text:
    return Text.assemble(("◆ ", theme.GOLD), (model_name, theme.MUTED))


class PromptBox(Vertical):
    """The input card: command list, text area, and a footer with the model."""

    def __init__(self, model_name: str = "gpt-4.1-mini", **kwargs) -> None:
        super().__init__(**kwargs)
        self.model_name = model_name

    def compose(self) -> ComposeResult:
        menu = CommandMenu(id="command-menu")
        yield menu
        yield PromptInput(
            placeholder="Ask Tyrion to build, fix, or explain something…",
            id="prompt-input",
            menu=menu,
        )
        with Horizontal(id="prompt-footer"):
            yield Label(_model_label(self.model_name), id="prompt-model-pill")
            yield Label(
                Text("↵ send   / commands   esc stop", style=theme.FAINT),
                id="prompt-hint",
            )

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        """Show the command list while the user is typing a `/command`."""
        self.query_one(CommandMenu).show_for(event.text_area.text)

    def set_model(self, model_name: str) -> None:
        """Update model name shown in the footer."""
        self.model_name = model_name
        try:
            self.query_one("#prompt-model-pill", Label).update(_model_label(model_name))
        except Exception:
            pass


class TUIStatusBar(Widget):
    """One quiet line: state, model, a token gauge, and where you are."""

    DEFAULT_CSS = """
    TUIStatusBar {
        dock: bottom;
        height: 1;
        width: 100%;
    }
    """

    session_id = reactive("")
    model = reactive("")
    cwd = reactive("")
    status_text = reactive("Idle")
    current_tokens = reactive(0)
    token_limit = reactive(0)

    def __init__(self, session_id: str, model: str, cwd: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.session_id = session_id
        self.model = model
        self.cwd = cwd

    def set_status(self, text: str) -> None:
        """Update the engine status."""
        self.status_text = text

    def set_tokens(self, current: int, limit: int) -> None:
        """Update the token usage count and limit."""
        self.current_tokens = current
        self.token_limit = limit

    def _tokens_segment(self, with_bar: bool = True) -> Text:
        if not self.token_limit:
            return Text.assemble(("tokens ", theme.FAINT), ("—", theme.MUTED))
        fraction = self.current_tokens / self.token_limit
        color = usage_color(fraction)
        segment = Text()
        if with_bar:
            filled, empty = token_bar(fraction)
            segment.append(filled, style=color)
            segment.append(empty, style=theme.BORDER_STRONG)
            segment.append("  ")
        segment.append(format_tokens(self.current_tokens), style=theme.TEXT if with_bar else color)
        segment.append(f" / {format_tokens(self.token_limit)}", style=theme.MUTED)
        return segment

    @staticmethod
    def _join(parts: list[Text], gap: str) -> Text:
        joined = Text()
        for index, part in enumerate(parts):
            if index:
                joined.append(gap, style=theme.FAINT)
            joined.append_text(part)
        return joined

    def render(self) -> Text:
        width = self.size.width
        state_color = {"Idle": theme.SAGE, "Error": theme.RED}.get(self.status_text, theme.GOLD)
        status = Text.assemble(("● ", state_color), (self.status_text, theme.TEXT))
        model = Text.assemble(("◆ ", theme.GOLD), (self.model or "no model", theme.TEXT))
        right_parts = [
            Text(truncate_left(shorten_home(self.cwd), 34), style=theme.MUTED),
            Text(self.session_id[:8], style=theme.FAINT),
        ]
        # What to show, most complete first. When the terminal is narrow, shed
        # detail in this order: session id, folder, the gauge bar, the model.
        candidates = [
            ([status, model, self._tokens_segment()], 2),
            ([status, model, self._tokens_segment()], 1),
            ([status, model, self._tokens_segment()], 0),
            ([status, model, self._tokens_segment(with_bar=False)], 0),
            ([status, self._tokens_segment(with_bar=False)], 0),
            ([status], 0),
        ]
        for left_parts, keep in candidates:
            left = self._join(left_parts, "  ·  ")
            right = self._join(right_parts[:keep], "  ·  ")
            if 2 + left.cell_len + (3 + right.cell_len if keep else 0) <= width:
                gap = width - 2 - left.cell_len - right.cell_len
                return Text.assemble(" ", left, " " * gap, right, " ", no_wrap=True)
        line = Text.assemble(" ", status, no_wrap=True)
        line.truncate(width, overflow="ellipsis")
        return line


class ThinkingIndicator(Static):
    """Shows that the model is generating a response."""

    def __init__(self, **kwargs) -> None:
        super().__init__("", **kwargs)
        self.visible = False
        self._frame = 0
        self._timer: Timer | None = None

    def on_mount(self) -> None:
        self._timer = self.set_interval(0.1, self._tick)
        self._paint()

    def _tick(self) -> None:
        if not self.visible:
            return  # nothing to animate while hidden
        self._frame = (self._frame + 1) % len(SPINNER_FRAMES)
        self._paint()

    def _paint(self) -> None:
        self.update(
            Text.assemble(
                (SPINNER_FRAMES[self._frame], theme.GOLD),
                ("  Thinking…", theme.MUTED),
                ("   esc to stop", theme.FAINT),
            )
        )


class MessageWidget(Static):
    """One chat message: your words, Tyrion's reply, a system note, or an error."""

    def __init__(self, role: str, text: str = "", show_label: bool = True, **kwargs) -> None:
        super().__init__(**kwargs)
        self.role = role
        self.text = text
        self.show_label = show_label
        self.add_class(f"role-{role}")
        self.update_content(text)

    def update_content(self, text: str) -> None:
        """Update message contents and re-render."""
        self.text = text
        self.update(self._build(text))

    def _build(self, text: str) -> RenderableType:
        if self.role == "user":
            return Text(text)
        if self.role == "assistant":
            parts: list[RenderableType] = []
            if self.show_label:
                parts.append(Text("◆ Tyrion", style=f"bold {theme.GOLD}"))
            if text:
                parts.append(theme.markdown(text))
            return Group(*parts) if parts else Text("")
        if self.role == "error":
            return Text.assemble(("✕ ", f"bold {theme.RED}"), (text, theme.TEXT))
        return theme.markdown(text)  # system notes


class ToolCallWidget(Static):
    """A tool call as one compact row: status, name, what it acts on, and its result."""

    def __init__(
        self,
        tool_name: str,
        args: dict[str, JSONValue],
        live: bool = False,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.tool_name = tool_name
        self.args = args
        self.live = live  # a call happening right now (not one replayed from history)
        self.result_text = ""
        self.is_error = False
        self.finished = False
        self._frame = 0
        self._started = time.monotonic()
        self._elapsed: float | None = None
        self._timer: Timer | None = None
        self._update_display()

    def on_mount(self) -> None:
        if not self.finished:
            self._timer = self.set_interval(0.1, self._tick)

    def _tick(self) -> None:
        self._frame = (self._frame + 1) % len(SPINNER_FRAMES)
        self._update_display()

    def set_result(self, result_text: str, is_error: bool = False) -> None:
        """Sets the execution outcome of the tool call."""
        self.result_text = result_text
        self.is_error = is_error
        self.finished = True
        if self.live:
            self._elapsed = time.monotonic() - self._started
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        self._update_display()

    def _update_display(self) -> None:
        if not self.finished:
            glyph, glyph_style = SPINNER_FRAMES[self._frame], theme.GOLD
        elif self.is_error:
            glyph, glyph_style = "✗", theme.RED
        else:
            glyph, glyph_style = "✓", theme.SAGE

        header = Text(no_wrap=True, overflow="ellipsis")
        header.append(f"{glyph} ", style=glyph_style)
        header.append(self.tool_name, style=f"bold {theme.TEXT}")
        summary = tool_summary(self.tool_name, self.args)
        if summary:
            header.append(f"  {summary}", style=theme.MUTED)
        if self._elapsed is not None:
            header.append(f"  {self._elapsed:.1f}s", style=theme.FAINT)
        if not self.finished:
            self.update(header)
            return

        lines, hidden = result_excerpt(self.tool_name, self.result_text, self.is_error)
        rail = theme.RED if self.is_error else theme.BORDER_STRONG
        body_style = theme.MUTED if not self.is_error else "#d98b8f"
        rows: list[RenderableType] = [header]
        for line in lines:
            row = Text(no_wrap=True, overflow="ellipsis")
            row.append("  │ ", style=rail)
            row.append(line, style=body_style)
            rows.append(row)
        if hidden:
            more = Text(no_wrap=True)
            more.append("  │ ", style=rail)
            more.append(f"… {hidden} more line{'s' if hidden != 1 else ''}", style=theme.FAINT)
            rows.append(more)
        self.update(Group(*rows))
