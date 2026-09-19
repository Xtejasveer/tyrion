"""Turning agent data into short, readable text. Shared by the TUI and the print mode."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from tyrion_agent.types import JSONValue
from tyrion_coding.theme import AMBER, RED, SAGE


def format_tokens(count: int) -> str:
    """842 -> '842', 41200 -> '41.2K', 128000 -> '128K', 1048576 -> '1.0M'."""
    if count < 1_000:
        return str(count)
    if count < 100_000:
        return f"{count / 1_000:.1f}K"
    if count < 999_500:
        return f"{round(count / 1_000)}K"
    return f"{count / 1_000_000:.1f}M"


def usage_color(fraction: float) -> str:
    """Green while there is room, amber getting close, red at the 80% compaction point."""
    if fraction >= 0.8:
        return RED
    if fraction >= 0.6:
        return AMBER
    return SAGE


def token_bar(fraction: float, width: int = 8) -> tuple[str, str]:
    """A small bar as (filled cells, empty cells), e.g. ('▰▰▰', '▱▱▱▱▱')."""
    fraction = min(max(fraction, 0.0), 1.0)
    filled = round(fraction * width)
    if fraction > 0 and filled == 0:
        filled = 1  # any use at all shows up
    return "▰" * filled, "▱" * (width - filled)


def shorten_home(path: str) -> str:
    """/Users/me/project -> ~/project"""
    home = str(Path.home())
    if path == home:
        return "~"
    if path.startswith(home + os.sep):
        return "~" + path[len(home) :]
    return path


def truncate(text: str, width: int) -> str:
    """Cut to `width` characters, ending with an ellipsis."""
    if width <= 0:
        return ""
    if len(text) <= width:
        return text
    return text[: width - 1] + "…" if width > 1 else text[:width]


def truncate_left(text: str, width: int) -> str:
    """Cut to `width` characters keeping the end (the interesting part of a path)."""
    if width <= 0:
        return ""
    if len(text) <= width:
        return text
    return "…" + text[-(width - 1) :] if width > 1 else text[-width:]


def tool_summary(name: str, args: Mapping[str, JSONValue], width: int = 80) -> str:
    """One line describing what a tool call is doing, e.g. the path or the command."""
    path = args.get("path")
    if name in ("read", "write", "edit") and isinstance(path, str):
        extra = ""
        edits = args.get("edits")
        if name == "edit" and isinstance(edits, list):
            extra = f" · {len(edits)} edit{'s' if len(edits) != 1 else ''}"
        return truncate_left(shorten_home(path), width - len(extra)) + extra

    command = args.get("command")
    if name == "bash" and isinstance(command, str):
        lines = command.strip().splitlines() or [""]
        more = " …" if len(lines) > 1 else ""
        return truncate(lines[0], width - len(more)) + more

    return truncate(", ".join(f"{key}={value!r}" for key, value in args.items()), width)


def result_excerpt(tool_name: str, text: str, is_error: bool) -> tuple[list[str], int]:
    """The few result lines worth showing, and how many more were left out.

    A successful read is just a line count (the model needs the contents, the
    person watching does not). Blank lines are dropped to keep this compact.
    """
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    if not lines:
        return [], 0
    if tool_name == "read" and not is_error:
        return [f"{len(lines)} line{'s' if len(lines) != 1 else ''}"], 0
    limit = 8 if is_error else 6
    return lines[:limit], max(0, len(lines) - limit)
