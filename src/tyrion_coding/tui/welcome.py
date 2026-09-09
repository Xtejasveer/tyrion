from __future__ import annotations

from textual.widgets import Static

TYRION_LOGO = """
[bold white] ▄█▄  █ █  █▀▄   ▄   █▀█  █▀▄[/]
[white]  █   ▀▄█  █ ▀   █   █ █  █ █[/]
[grey62]  ▀▄    █  ▀     ▀   █▄█  █ █[/]
"""


class WelcomeHeader(Static):
    """Centered pixel ASCII logo for Tyrion."""

    def __init__(self, **kwargs) -> None:
        super().__init__(TYRION_LOGO.strip(), **kwargs)


class WelcomeHints(Static):
    """Keyboard shortcuts underneath the input box."""

    def __init__(self, **kwargs) -> None:
        text = "[bold white]tab[/bold white] [dim]autocomplete[/dim]   [bold white]/[/bold white] [dim]commands[/dim]"
        super().__init__(text, **kwargs)


class WelcomeTip(Static):
    """Bottom tip pointing to /connect."""

    def __init__(self, **kwargs) -> None:
        text = "● [bold #f59e0b]Tip[/bold #f59e0b] Run [bold white]/connect[/bold white] to add an AI provider and start coding"
        super().__init__(text, **kwargs)
