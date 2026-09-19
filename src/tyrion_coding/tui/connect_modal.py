from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select

from tyrion_coding import theme
from tyrion_coding.tui.styles import css


class ConnectModal(ModalScreen[tuple[str, str] | None]):
    """Modal screen allowing the user to choose a model provider and enter their API key."""

    CSS = css("""
    ConnectModal {
        align: center middle;
        background: %BG_DEEP% 75%;
    }

    #connect-dialog {
        width: 62;
        height: auto;
        background: transparent;
        border: round %GOLD_DIM%;
    }

    #connect-body {
        height: auto;
        background: %SURFACE%;
        padding: 1 3;
    }

    #connect-title {
        width: 100%;
        text-style: bold;
        color: %GOLD%;
    }

    #connect-subtitle {
        width: 100%;
        color: %MUTED%;
        margin-bottom: 1;
    }

    .section-label {
        margin-top: 1;
        color: %FAINT%;
        text-style: bold;
    }

    #provider-select {
        width: 100%;
    }

    #key-input {
        width: 100%;
        background: %BG%;
        border: round %BORDER_STRONG%;
    }

    #key-input:focus {
        border: round %GOLD%;
    }

    #connect-btn {
        width: 100%;
        margin-top: 2;
    }

    #connect-footer {
        width: 100%;
        margin-top: 1;
        content-align: center middle;
    }
    """)

    def __init__(self) -> None:
        super().__init__()
        self._selected_provider = "openrouter"

    def compose(self) -> ComposeResult:
        with Vertical(id="connect-dialog"), Vertical(id="connect-body"):
            yield Label("◆ Connect a provider", id="connect-title")
            yield Label(
                "Add an API key to start chatting. It is saved on this machine.",
                id="connect-subtitle",
            )
            yield Label("PROVIDER", classes="section-label")
            yield Select(
                options=[
                    ("OpenRouter · Claude, GPT-4, Gemini, Llama", "openrouter"),
                    ("OpenAI direct", "openai"),
                    ("DeepSeek", "deepseek"),
                ],
                value="openrouter",
                allow_blank=False,
                id="provider-select",
            )
            yield Label("API KEY", classes="section-label")
            yield Input(
                placeholder="Paste your key here (e.g. sk-or-v1-…)",
                password=True,
                id="key-input",
            )
            yield Button("Connect", variant="primary", id="connect-btn")
            yield Label(
                Text.assemble(
                    ("enter", f"bold {theme.GOLD}"), (" connect", theme.MUTED),
                    ("     ", ""),
                    ("esc", f"bold {theme.GOLD}"), (" cancel", theme.MUTED),
                ),
                id="connect-footer",
            )

    def on_mount(self) -> None:
        """Focus the key input field and pre-fill existing credentials if available."""
        from tyrion_coding.provider_config import load_saved_credentials
        key_input = self.query_one("#key-input", Input)
        saved = load_saved_credentials()
        if "openrouter" in saved:
            key_input.value = saved["openrouter"]
        key_input.focus()

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
        val = provider_select.value
        if val is None or val == Select.BLANK:
            selected_provider = "openrouter"
        else:
            selected_provider = str(val)

        self.dismiss((selected_provider, key))

    def action_cancel(self) -> None:
        """Dismiss on Escape."""
        self.dismiss(None)

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]
