"""Pop up window for choosing a past session to resume."""

from __future__ import annotations

from datetime import UTC, datetime

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, OptionList
from textual.widgets.option_list import Option

from tyrion_coding import theme
from tyrion_coding.session_coding import SessionManager, SessionMeta
from tyrion_coding.tui.styles import css


def _row(meta: SessionMeta) -> Text:
    """One session as a single line: when, which model, how much, and its id."""
    empty = meta.message_count == 0
    stamp = meta.created_at.astimezone().strftime("%b %d  %H:%M") if meta.created_at else "unknown date"
    count = "empty" if empty else f"{meta.message_count} messages"
    return Text.assemble(
        (stamp, theme.FAINT if empty else theme.TEXT),
        ("   ", ""),
        (meta.model or "unknown model", theme.FAINT if empty else theme.GOLD_SOFT),
        ("   ", ""),
        (count, theme.FAINT),
        ("   ", ""),
        (meta.session_id[:8], theme.FAINT),
    )


class SessionPickerModal(ModalScreen[str | None]):
    """Modal screen displaying past sessions for the user to select and resume."""

    CSS = css("""
    SessionPickerModal {
        align: center middle;
        background: %BG_DEEP% 75%;
    }

    #picker-dialog {
        width: 86;
        max-width: 96%;
        height: auto;
        max-height: 80%;
        background: transparent;
        border: round %GOLD_DIM%;
    }

    #picker-body {
        height: auto;
        background: %SURFACE%;
        padding: 1 2;
    }

    #picker-title {
        width: 100%;
        text-style: bold;
        color: %GOLD%;
        margin-bottom: 1;
    }

    #session-list {
        height: auto;
        max-height: 20;
        background: transparent;
        border: none;
        padding: 0;
    }

    #session-list > .option-list--option-highlighted {
        background: %GOLD_TINT%;
        text-style: bold;
    }

    #picker-footer {
        width: 100%;
        margin-top: 1;
    }
    """)

    def compose(self) -> ComposeResult:
        with Vertical(id="picker-dialog"), Vertical(id="picker-body"):
            yield Label("◆ Resume a session", id="picker-title")
            yield OptionList(id="session-list")
            yield Label(
                Text.assemble(
                    ("↑↓", f"bold {theme.GOLD}"), (" move", theme.MUTED),
                    ("     ", ""),
                    ("enter", f"bold {theme.GOLD}"), (" resume", theme.MUTED),
                    ("     ", ""),
                    ("esc", f"bold {theme.GOLD}"), (" cancel", theme.MUTED),
                ),
                id="picker-footer",
            )

    def on_mount(self) -> None:
        """Populate the options list with existing sessions, newest first."""
        option_list = self.query_one("#session-list", OptionList)
        manager = SessionManager()
        oldest = datetime.min.replace(tzinfo=UTC)
        newest_first = sorted(
            manager.list_sessions(),
            key=lambda meta: meta.created_at or oldest,
            reverse=True,
        )
        # Sessions with something in them first; the empty ones (nothing to resume) last.
        sessions = [m for m in newest_first if m.message_count] + [
            m for m in newest_first if not m.message_count
        ]

        if not sessions:
            option_list.add_option(
                Option(Text("No saved sessions yet", style=theme.FAINT), id="none", disabled=True)
            )
            return

        for meta in sessions:
            option_list.add_option(Option(_row(meta), id=meta.session_id))
        option_list.highlighted = 0  # the newest session is ready: Enter resumes it
        option_list.focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Handle selecting an option."""
        if event.option.id == "none":
            self.dismiss(None)
        else:
            self.dismiss(event.option.id)

    def action_cancel(self) -> None:
        """Dismiss without selection when Escape is pressed."""
        self.dismiss(None)

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]
