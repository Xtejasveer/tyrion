"""The palette: valid colors, readable contrast, and the pieces built from it."""

from __future__ import annotations

import io
import re

import pytest
from rich.console import Console

from tyrion_coding import theme
from tyrion_coding.tui.styles import APP_CSS, TYRION_THEME, css

PALETTE = {
    name: value
    for name, value in vars(theme).items()
    if name.isupper() and isinstance(value, str) and value.startswith("#")
}


def _luminance(color: str) -> float:
    def channel(value: int) -> float:
        v = value / 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = (int(color[i : i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def _contrast(fg: str, bg: str) -> float:
    lighter, darker = sorted((_luminance(fg), _luminance(bg)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def test_every_palette_entry_is_a_valid_hex_color() -> None:
    assert len(PALETTE) >= 20  # the palette was actually found
    for name, value in PALETTE.items():
        assert re.fullmatch(r"#[0-9a-fA-F]{6}", value), f"{name} = {value!r}"


SURFACES = ("BG", "SURFACE", "RAISED")


@pytest.mark.parametrize("surface", SURFACES)
@pytest.mark.parametrize("color", ["TEXT", "MUTED", "GOLD", "SAGE", "AMBER", "RED", "AZURE"])
def test_text_colors_are_readable_on_every_surface(color: str, surface: str) -> None:
    """WCAG AA (4.5:1) for everything meant to be read."""
    assert _contrast(PALETTE[color], PALETTE[surface]) >= 4.5, f"{color} on {surface}"


@pytest.mark.parametrize("surface", ["BG", "SURFACE"])
def test_tertiary_text_stays_legible(surface: str) -> None:
    assert _contrast(theme.FAINT, PALETTE[surface]) >= 3.5


def test_specific_pairings_used_by_the_interface_are_readable() -> None:
    pairs = {
        "selected command row": (theme.GOLD, theme.GOLD_TINT),
        "selected command description": (theme.TEXT, theme.GOLD_TINT),
        "inline code": (theme.GOLD_SOFT, theme.RAISED),
        "error text": (theme.RED, theme.RED_TINT),
        "button label": (theme.BG, theme.GOLD),
        "code comments": (theme.COMMENT, theme.CODE_BG),
    }
    for label, (fg, bg) in pairs.items():
        assert _contrast(fg, bg) >= 4.5, label


def test_lerp_color() -> None:
    assert theme.lerp_color("#000000", "#ffffff", 0) == "#000000"
    assert theme.lerp_color("#000000", "#ffffff", 1) == "#ffffff"
    assert theme.lerp_color("#000000", "#ffffff", 0.5) == "#808080"
    assert theme.lerp_color("#ff0000", "#0000ff", 0.5) == "#800080"


def test_css_fills_every_placeholder() -> None:
    assert css("a { color: %GOLD%; background: %BG%; }") == f"a {{ color: {theme.GOLD}; background: {theme.BG}; }}"
    assert not re.search(r"%[A-Z_]+%", APP_CSS)  # no placeholder was left unfilled


def test_css_rejects_an_unknown_color_name() -> None:
    with pytest.raises(AttributeError):
        css("a { color: %NOPE%; }")


def test_textual_theme_uses_the_palette() -> None:
    assert TYRION_THEME.primary == theme.GOLD
    assert TYRION_THEME.background == theme.BG
    assert TYRION_THEME.error == theme.RED
    assert TYRION_THEME.dark is True


def _render(renderable) -> str:
    console = Console(file=io.StringIO(), width=60, force_terminal=False, theme=theme.RICH_THEME)
    with console.capture() as capture:
        console.print(renderable)
    return capture.get()


def test_markdown_renders_headings_left_aligned() -> None:
    out = _render(theme.markdown("# Title\n\nbody"))
    title_line = next(line for line in out.splitlines() if "Title" in line)
    assert title_line.startswith("Title")  # Rich would center a top-level heading


def test_markdown_renders_code_lists_and_quotes() -> None:
    out = _render(theme.markdown("- one\n- two\n\n```python\nx = 1\n```\n\n> quoted"))
    for expected in ("one", "two", "x = 1", "quoted"):
        assert expected in out


def test_markdown_survives_text_that_looks_like_markup() -> None:
    out = _render(theme.markdown("a [/bold] and [red]tag[/red] stay literal"))
    assert "[/bold]" in out
    assert "[red]tag[/red]" in out
