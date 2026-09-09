from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select


class ConnectModal(ModalScreen[tuple[str, str] | None]):
    """Modal screen allowing the user to choose a model provider and enter their API key."""

    CSS = """
    ConnectModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }

    #connect-dialog {
        width: 66;
        height: auto;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }

    #connect-title {
        text-align: center;
        width: 100%;
        margin-bottom: 1;
        text-style: bold;
        color: $primary;
    }

    .section-label {
        margin-top: 1;
        margin-bottom: 0;
        text-style: bold;
        color: $text;
    }

    #provider-select {
        margin-bottom: 1;
        width: 100%;
    }

    #key-input {
        margin-bottom: 1;
        border: tall $primary;
        width: 100%;
    }

    #connect-btn {
        width: 100%;
        margin-top: 1;
        margin-bottom: 1;
    }

    #connect-footer {
        text-align: center;
        width: 100%;
        color: $text-muted;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._selected_provider = "openrouter"

    def compose(self) -> ComposeResult:
        with Vertical(id="connect-dialog"):
            yield Label("⚡ Connect Model Provider", id="connect-title")
            yield Label("1. Select Provider:", classes="section-label")
            yield Select(
                options=[
                    ("OpenRouter (Claude, GPT-4, Gemini, Llama)", "openrouter"),
                    ("OpenAI Direct", "openai"),
                    ("DeepSeek", "deepseek"),
                ],
                value="openrouter",
                allow_blank=False,
                id="provider-select",
            )
            yield Label("2. Enter API Key:", classes="section-label")
            yield Input(
                placeholder="Paste your API key here (e.g. sk-or-v1-...)",
                id="key-input",
            )
            yield Button("Connect & Start Chatting", variant="primary", id="connect-btn")
            yield Label(
                "Press Enter in key box to Connect | Escape to Cancel",
                id="connect-footer",
            )

    def on_mount(self) -> None:
        """Focus the key input field automatically on mount."""
        self.query_one("#key-input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button click."""
        if event.button.id == "connect-btn":
            self._submit()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key pressed inside the Input box."""
        self._submit()

    def _submit(self) -> None:
        key_input = self.query_one("#key-input", Input)
        key = key_input.value.strip()
        if not key:
            self.notify("API key cannot be empty!", severity="error")
            key_input.focus()
            return

        provider_select = self.query_one("#provider-select", Select)
        selected_provider = str(provider_select.value) if provider_select.value else "openrouter"

        self.dismiss((selected_provider, key))

    def action_cancel(self) -> None:
        """Dismiss on Escape."""
        self.dismiss(None)

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]