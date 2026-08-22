"""Command registry and handlers for slash commands."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, Awaitable, Callable

if TYPE_CHECKING:
    from tyrion_coding.tui.app import TyrionApp

@dataclass(frozen=True, slots=True)
class SlashCommand:
    name: str
    description: str
    handler: Callable[[TyrionApp, list[str]], Awaitable[None]]

class CommandRegistry:
    """Registry of interactive slash commands."""

    def __init__(self) -> None:
        self._commands: dict[str, SlashCommand] ={}

    def register(self, command: SlashCommand) -> None:
        self._commands[command.name] = command

    def get(self, name:str) -> SlashCommand | None:
        return self._commands.get(name)

    @property
    def commands(self) -> list[SlashCommand]:
        return list(self._commands.values())

registry = CommandRegistry()

## Command Handlers ---
async def handle_help(app:TyrionApp, args: list[str]) -> None:
    """Display available commands."""
    lines = []
    for cmd in sorted(registry.commands, key = lambda c: c.name):
        lines.append(f"[bold]{cmd.name}[/bold] - {cmd.description}")

    from tyrion_coding.tui.widgets import MessageWidget
    help_widget = MessageWidget(
        role="system",
        content = "### Available Commands\n\n" + "\n".join(f"-{line}" for line in lines),
    )
    await app.transcript_view.mount(help_widget)
    app.transcript_view.scroll_end()

async def handle_clear(app: TyrionApp, args: list[str]) -> None:
    """Clear the transcript."""
    await app.clear_transcript()

async def handle_quit(app: TyrionApp, args: list[str]) -> None:
    """Exit the application"""
    app.exit()

async def handle_model(app: TyrionApp, args: list[str]) -> None:
    """Switch the model."""
    from tyrion_coding.tui.widgets import MessageWidget
    if not args:
        active_model = app.session.harness.config.model
        msg_widget = MessageWidget(
            role = "system",
            content = f"Active model: [green]{active_model}[/green]\n\nUsage: '/model<name>'"
        )
        await app.transcript_view.mount(msg_widget)
    else:
        new_model = args[0]
        app.session.harness.config.model = new_model
        app.status_bar.model = new_model
        app.status_bar._update_status()
        msg_widget = MessageWidget(
            role = "system",
            content = f"Switched model to [green]{new_model}[/green]"
        )
        await app.transcript_view.mount(msg_widget)
    app.transcript_view.scroll_end()

async def handle_resume(app: TyrionApp, args: list[str]) -> None:
    """Trigger the session picker screen."""
    from tyrion_coding.tui.picker import SessionPickerModal
    session_id = await app.push_screen(SessionPickerModal())
    if session_id:
        app.run_resume_worker(session_id)

#Registry defaults 
registry.register(SlashCommand("/help", "List available commands", handle_help))
registry.register(SlashCommand("/clear", "Clear chat transcript history", handle_clear))
registry.register(SlashCommand("/quit", "Exit the TUI", handle_quit))
registry.register(SlashCommand("/exit", "Exit the TUI", handle_quit))
registry.register(SlashCommand("/model", "Switch LLM model, e.g. `/model gpt-4o`", handle_model))
registry.register(SlashCommand("/resume", "Show previous session selector modal", handle_resume))
