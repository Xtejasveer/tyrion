from __future__ import annotations

from rich.text import Text
from textual.widget import Widget
from textual.widgets import Static

from tyrion_coding import theme

# The wordmark, one letter at a time (6 rows each), so it is easy to keep aligned.
_LETTERS = {
    "T": ["████████╗", "╚══██╔══╝", "   ██║   ", "   ██║   ", "   ██║   ", "   ╚═╝   "],
    "Y": ["██╗   ██╗", "╚██╗ ██╔╝", " ╚████╔╝ ", "  ╚██╔╝  ", "   ██║   ", "   ╚═╝   "],
    "R": ["██████╗ ", "██╔══██╗", "██████╔╝", "██╔══██╗", "██║  ██║", "╚═╝  ╚═╝"],
    "I": ["██╗", "██║", "██║", "██║", "██║", "╚═╝"],
    "O": [" ██████╗ ", "██╔═══██╗", "██║   ██║", "██║   ██║", "╚██████╔╝", " ╚═════╝ "],
    "N": ["███╗   ██╗", "████╗  ██║", "██╔██╗ ██║", "██║╚██╗██║", "██║ ╚████║", "╚═╝  ╚═══╝"],
}
WORDMARK = ["".join(_LETTERS[letter][row] for letter in "TYRION") for row in range(6)]
WORDMARK_WIDTH = len(WORDMARK[0])

# Gold at the top, through amber, to crimson at the bottom.
_GRADIENT = ("#f2cd72", "#e0834a", theme.CRIMSON)
COMPACT_HEIGHT = 30  # below this many rows, use the one-line wordmark


def _gradient_at(t: float) -> str:
    """Color at position t (0..1) along the three-stop gradient."""
    if t <= 0.5:
        return theme.lerp_color(_GRADIENT[0], _GRADIENT[1], t * 2)
    return theme.lerp_color(_GRADIENT[1], _GRADIENT[2], (t - 0.5) * 2)


class WelcomeHeader(Widget):
    """The Tyrion wordmark in a gold-to-crimson gradient, with a tagline."""

    DEFAULT_CSS = """
    WelcomeHeader {
        width: 100%;
        height: auto;
    }
    """

    def render(self) -> Text:
        room_for_full = self.size.width >= WORDMARK_WIDTH + 2 and self.app.size.height >= COMPACT_HEIGHT
        logo = Text(justify="center", no_wrap=True)
        if room_for_full:
            for row, line in enumerate(WORDMARK):
                logo.append(line, style=_gradient_at(row / (len(WORDMARK) - 1)))
                logo.append("\n")
        else:
            spaced = "T  Y  R  I  O  N"
            for index, char in enumerate(spaced):
                logo.append(char, style=f"bold {_gradient_at(index / (len(spaced) - 1))}")
            logo.append("\n")
        logo.append("\n")
        logo.append("your terminal coding agent", style=theme.MUTED)
        return logo


def _chip(key: str, label: str) -> Text:
    return Text.assemble((key, f"bold {theme.GOLD}"), (f" {label}", theme.MUTED))


class WelcomeHints(Static):
    """Keyboard shortcuts underneath the input box."""

    def __init__(self, **kwargs) -> None:
        hints = Text(justify="center")
        for index, (key, label) in enumerate(
            [("/", "commands"), ("tab", "complete"), ("esc", "stop"), ("ctrl+c", "quit")]
        ):
            if index:
                hints.append("     ")
            hints.append_text(_chip(key, label))
        super().__init__(hints, **kwargs)


class WelcomeTip(Static):
    """Bottom tip pointing to /connect."""

    def __init__(self, **kwargs) -> None:
        tip = Text.assemble(
            ("✦ ", theme.GOLD_DIM),
            ("New here? Run ", theme.FAINT),
            ("/connect", f"bold {theme.MUTED}"),
            (" to add an AI provider and start coding", theme.FAINT),
            justify="center",
        )
        super().__init__(tip, **kwargs)
