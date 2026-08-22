"""Pop up window for selecting model provider ."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Grid
from textual.screen import ModalScreen
from textual.widgets import Label, OptionList
from textual.widgets.option_list import Option

from tyrion_coding.session_coding import SessionManager

class SessionPickerModal(ModalScreen[str | None]):
    """Modal screen displaying past sessions for the user to select and resume."""
    CSS = """
        SessionPickerModal {
            align: center middle;
            background: rgba(0, 0, 0, 0.5);
        }
        #picker-grid {
            width: 65;
            height: 32;
            border: thick $primary;
            background: $surface;
            padding: 1 2;
        }
        #picker-title {
            text-align: center;
            width: 100%;
            margin-bottom: 1;
            text-style: bold;
        }
        OptionList {
            border: solid $primary-darken-3;
            height: 1fr;
        }
        #picker-footer {
            text-align: center;
            margin-top: 1;
            color: $text-muted;
        }
        """
    def compose(self) -> ComposeResult:
        with Grid(id="picker-grid"):
            yield Label("Select a session to resume", id = "picker-title")
            yield OptionList(id = "session-list")
            yield Label("Press Enter to Select | Escape to Cancel",id = "picker-footer")

    def on_mount(self) -> None:
        """Populate the options list with exisiting sesions."""
        option_list = self.query_one("#session-list", OptionList)
        manager = SessionManager()
        sessions = manager.list_sessions()

        if not sessions:
            option_list.add_option(Option("No saved sessions found", id = "none", disabled = True))
            return

        for meta in sessions:
            created_str = ""
            if meta.created_at:
                created_str = meta.created_at.strftime("%Y-%m-%d %H:%M")

            prompt_line = (
                f"{meta.session_id[:8]}... |"
                f"Model: {meta.model or "unknown"} |"
                f"Messages: {meta.message_count} |"
                f"Date: {created_str}"
            )
            option_list.add_option(Option(prompt_line, id=meta.session_id))

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Handle selecting an option."""
        if event.option.id == "None":
            self.dismiss(None)
        else:
            self.dismiss(event.option.id)

    def action_cancel(self) -> None:
        """Dismiss without selection when Escape is pressed."""
        self.dismiss(None)
    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]
