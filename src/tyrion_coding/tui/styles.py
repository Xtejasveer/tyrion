"""The TUI's Textual theme and stylesheet, built from the palette in tyrion_coding.theme."""

from __future__ import annotations

import re

from textual.theme import Theme

from tyrion_coding import theme


def css(template: str) -> str:
    """Fill `%NAME%` placeholders in a stylesheet with colors from the palette."""
    return re.sub(r"%([A-Z_]+)%", lambda match: getattr(theme, match.group(1)), template)


# Makes Textual's built-in widgets (inputs, selects, buttons, lists) match too.
TYRION_THEME = Theme(
    name="tyrion",
    primary=theme.GOLD,
    secondary=theme.CRIMSON,
    accent=theme.AZURE,
    warning=theme.AMBER,
    error=theme.RED,
    success=theme.SAGE,
    foreground=theme.TEXT,
    background=theme.BG,
    surface=theme.SURFACE,
    panel=theme.RAISED,
    dark=True,
    variables={
        "border": theme.GOLD,
        "border-blurred": theme.BORDER_STRONG,
        "input-cursor-background": theme.GOLD,
        "input-cursor-foreground": theme.BG,
        "input-selection-background": f"{theme.GOLD} 30%",
        "block-cursor-background": theme.GOLD_TINT,
        "block-cursor-foreground": theme.GOLD,
        "block-cursor-text-style": "bold",
        "footer-background": theme.BG_DEEP,
    },
)

APP_CSS = css("""
Screen {
    background: %BG%;
    align: center middle;
}

* {
    scrollbar-size-vertical: 1;
    scrollbar-background: %BG%;
    scrollbar-color: %BORDER%;
    scrollbar-color-hover: %BORDER_STRONG%;
    scrollbar-color-active: %GOLD_DIM%;
}

/* ---- welcome screen ---- */

#welcome-wrapper {
    width: 84;
    max-width: 100%;
    height: auto;
}

#welcome-header {
    text-align: center;
    margin-bottom: 2;
}

#welcome-hints {
    width: 100%;
    height: 1;
    margin-top: 1;
    text-align: center;
}

#welcome-tip {
    width: 100%;
    height: 1;
    margin-top: 2;
    text-align: center;
}

/* ---- the prompt card ---- */

#prompt-box {
    width: 100%;
    height: auto;
    background: transparent;
    border: round %BORDER_STRONG%;
    padding: 0;
}

#prompt-box:focus-within {
    border: round %GOLD_DIM%;
}

/* The fill lives on the children so the rounded corners blend into the screen. */
#prompt-box > * {
    background: %SURFACE%;
}

#prompt-input {
    height: auto;
    min-height: 2;
    max-height: 10;
    padding: 0 1;
    border: none;
}

#prompt-input:focus {
    border: none;
    background: %SURFACE%;
}

#prompt-input .text-area--cursor-line {
    background: transparent;
}

#prompt-input .text-area--placeholder {
    color: %FAINT%;
}

#prompt-footer {
    height: 1;
    padding: 0 1;
}

#prompt-model-pill {
    width: 1fr;
}

#prompt-hint {
    display: none;
    width: auto;
}

.chat-active #prompt-hint {
    display: block;
}

/* ---- the conversation ---- */

#transcript-container {
    display: none;
    height: 1fr;
    padding: 0 2;
    border: none;
}

#thinking {
    display: none;
    height: 1;
    margin: 0 2;
    padding: 0 2;
}

MessageWidget {
    width: 100%;
    height: auto;
    margin: 1 0;
    link-color: %AZURE%;
    link-style: underline;
    link-color-hover: %GOLD%;
}

MessageWidget.role-user {
    background: %RAISED%;
    border-left: outer %BORDER_STRONG%;
    padding: 0 2 0 1;
}

MessageWidget.role-assistant {
    padding: 0 2;
}

MessageWidget.role-system {
    color: %MUTED%;
    border-left: outer %BORDER_STRONG%;
    padding: 0 2 0 1;
}

MessageWidget.role-error {
    background: %RED_TINT%;
    border-left: outer %RED%;
    padding: 0 2 0 1;
}

ToolCallWidget {
    width: 100%;
    height: auto;
    padding: 0 2;
}

/* ---- chat mode: the welcome furniture steps aside ---- */

Screen.chat-active,
.chat-active {
    align: left top;
}

.chat-active #welcome-header,
.chat-active #welcome-hints,
.chat-active #welcome-tip {
    display: none;
}

.chat-active #transcript-container {
    display: block;
    height: 1fr;
}

.chat-active #thinking {
    display: block;
}

.chat-active #welcome-wrapper {
    width: 100%;
    margin: 0 2 1 2;
}
""")
