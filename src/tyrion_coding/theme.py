"""Tyrion's look: one palette, shared by the TUI and the one-shot print mode.

Warm ink-black with Lannister gold and crimson. To retheme the whole app, change
the colors in this file (and nothing else).
"""

from __future__ import annotations

from pygments.style import Style as PygmentsStyle
from pygments.token import (
    Comment,
    Error,
    Generic,
    Keyword,
    Name,
    Number,
    Operator,
    Punctuation,
    String,
    Token,
)
from rich.markdown import Heading, Markdown
from rich.syntax import PygmentsSyntaxTheme
from rich.theme import Theme as RichTheme

# --- surfaces ---------------------------------------------------------------
BG = "#0e0d10"  # the screen
BG_DEEP = "#0a090c"  # status bar, behind modals
SURFACE = "#16151a"  # prompt box, dialogs
RAISED = "#1e1c23"  # user messages, inline code, hovered rows
BORDER = "#2b2932"
BORDER_STRONG = "#3b3843"

# --- text -------------------------------------------------------------------
TEXT = "#ebe6dc"
MUTED = "#8d8894"
FAINT = "#75707f"  # tertiary text; still 4:1 on the screen colors
COMMENT = "#837e8e"  # code comments (4.5:1 on CODE_BG)

# --- brand ------------------------------------------------------------------
GOLD = "#e0b04f"
GOLD_SOFT = "#e6c068"
GOLD_DIM = "#8a6a2b"
GOLD_TINT = "#2a2314"  # background of the highlighted row
CRIMSON = "#c0424f"

# --- meaning ----------------------------------------------------------------
SAGE = "#8fbf7a"  # success, idle
AMBER = "#e59f4a"  # warning
RED = "#ef5f67"  # error
RED_TINT = "#241315"
AZURE = "#79b4d6"  # links, info

# Same look as SURFACE with a touch more depth, for code blocks.
CODE_BG = "#131217"


def lerp_color(start: str, end: str, t: float) -> str:
    """The color `t` (0..1) of the way from `start` to `end`, as #rrggbb."""
    a = [int(start[i : i + 2], 16) for i in (1, 3, 5)]
    b = [int(end[i : i + 2], 16) for i in (1, 3, 5)]
    mixed = [round(x + (y - x) * t) for x, y in zip(a, b)]
    return "#" + "".join(f"{value:02x}" for value in mixed)


# --- markdown and code ------------------------------------------------------


class TyrionCodeStyle(PygmentsStyle):
    """Syntax colors for fenced code blocks."""

    background_color = CODE_BG
    styles = {  # noqa: RUF012  (pygments reads this as a class attribute)
        Token: TEXT,
        Comment: f"italic {COMMENT}",
        Keyword: "#d9707d",
        Keyword.Constant: AMBER,
        Operator: MUTED,
        Punctuation: MUTED,
        Name.Function: GOLD_SOFT,
        Name.Class: f"bold {GOLD_SOFT}",
        Name.Decorator: AZURE,
        Name.Builtin: AZURE,
        Name.Exception: RED,
        String: SAGE,
        String.Escape: AMBER,
        String.Interpol: AMBER,
        Number: AMBER,
        Generic.Deleted: RED,
        Generic.Inserted: SAGE,
        Generic.Heading: f"bold {GOLD}",
        Error: RED,
    }


RICH_THEME = RichTheme(
    {
        "markdown.code": f"{GOLD_SOFT} on {RAISED}",
        "markdown.code_block": TEXT,
        "markdown.h1": f"bold {GOLD}",
        "markdown.h2": f"bold {GOLD}",
        "markdown.h3": f"bold {TEXT}",
        "markdown.h4": f"bold {MUTED}",
        "markdown.h5": f"bold {MUTED}",
        "markdown.h6": f"bold {MUTED}",
        "markdown.item.bullet": GOLD,
        "markdown.item.number": GOLD,
        "markdown.block_quote": f"italic {MUTED}",
        "markdown.hr": FAINT,
        "markdown.link": AZURE,
        "markdown.link_url": f"underline {AZURE}",
    }
)


class _LeftHeading(Heading):
    """Rich centers top-level headings; a chat reads better left-aligned."""

    LEVEL_ALIGN = {**Heading.LEVEL_ALIGN, "h1": "left"}  # noqa: RUF012


class TyrionMarkdown(Markdown):
    elements = {**Markdown.elements, "heading_open": _LeftHeading}  # noqa: RUF012


def markdown(text: str) -> Markdown:
    """Markdown in Tyrion's colors. Needs RICH_THEME on the console that renders it."""
    return TyrionMarkdown(text, code_theme=PygmentsSyntaxTheme(TyrionCodeStyle))
