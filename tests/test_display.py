"""Display helpers: token formatting, path shortening, tool summaries, result excerpts."""

from __future__ import annotations

import pytest

from tyrion_coding import theme
from tyrion_coding.display import (
    format_tokens,
    result_excerpt,
    shorten_home,
    token_bar,
    tool_summary,
    truncate,
    truncate_left,
    usage_color,
)


@pytest.mark.parametrize(
    ("count", "shown"),
    [
        (0, "0"),
        (842, "842"),
        (1_000, "1.0K"),
        (41_200, "41.2K"),
        (99_949, "99.9K"),
        (128_000, "128K"),
        (999_400, "999K"),
        (1_048_576, "1.0M"),
        (2_000_000, "2.0M"),
    ],
)
def test_format_tokens(count: int, shown: str) -> None:
    assert format_tokens(count) == shown


def test_usage_color_warns_before_the_compaction_point() -> None:
    assert usage_color(0.0) == theme.SAGE
    assert usage_color(0.59) == theme.SAGE
    assert usage_color(0.6) == theme.AMBER
    assert usage_color(0.79) == theme.AMBER
    assert usage_color(0.8) == theme.RED  # where auto-compaction kicks in
    assert usage_color(1.5) == theme.RED


def test_token_bar() -> None:
    assert token_bar(0.0, 8) == ("", "▱" * 8)
    assert token_bar(0.5, 8) == ("▰" * 4, "▱" * 4)
    assert token_bar(1.0, 8) == ("▰" * 8, "")
    assert token_bar(3.0, 8) == ("▰" * 8, "")  # never overflows
    assert token_bar(0.001, 8) == ("▰", "▱" * 7)  # any use at all shows


def test_shorten_home(monkeypatch) -> None:
    monkeypatch.setenv("HOME", "/Users/someone")
    assert shorten_home("/Users/someone") == "~"
    assert shorten_home("/Users/someone/proj/app") == "~/proj/app"
    assert shorten_home("/Users/someone2/proj") == "/Users/someone2/proj"  # not a prefix match
    assert shorten_home("/etc/hosts") == "/etc/hosts"


def test_truncate() -> None:
    assert truncate("short", 10) == "short"
    assert truncate("a long sentence", 6) == "a lon…"
    assert truncate("anything", 1) == "a"
    assert truncate("anything", 0) == ""


def test_truncate_left_keeps_the_end() -> None:
    assert truncate_left("src/deeply/nested/file.py", 12) == "…ted/file.py"
    assert truncate_left("file.py", 12) == "file.py"
    assert truncate_left("anything", 1) == "g"
    assert truncate_left("anything", 0) == ""


class TestToolSummary:
    def test_file_tools_show_the_path(self, monkeypatch) -> None:
        monkeypatch.setenv("HOME", "/Users/someone")
        assert tool_summary("read", {"path": "src/app.py"}) == "src/app.py"
        assert tool_summary("write", {"path": "/Users/someone/notes.md", "content": "x"}) == "~/notes.md"

    def test_edit_counts_the_edits(self) -> None:
        one = tool_summary("edit", {"path": "a.py", "edits": [{"oldText": "x", "newText": "y"}]})
        two = tool_summary("edit", {"path": "a.py", "edits": [{}, {}]})
        assert one == "a.py · 1 edit"
        assert two == "a.py · 2 edits"

    def test_bash_shows_the_first_line_of_the_command(self) -> None:
        assert tool_summary("bash", {"command": "pytest -q"}) == "pytest -q"
        assert tool_summary("bash", {"command": "cd app\nmake test"}) == "cd app …"

    def test_long_values_are_cut_to_the_width(self) -> None:
        summary = tool_summary("bash", {"command": "x" * 200}, width=40)
        assert len(summary) == 40
        assert summary.endswith("…")

    def test_unknown_tools_fall_back_to_key_value_pairs(self) -> None:
        assert tool_summary("grep", {"pattern": "todo", "n": 3}) == "pattern='todo', n=3"
        assert tool_summary("noargs", {}) == ""

    def test_a_missing_or_odd_path_does_not_crash(self) -> None:
        assert tool_summary("read", {}) == ""
        assert tool_summary("read", {"path": 5}) == "path=5"


class TestResultExcerpt:
    def test_short_results_are_shown_whole(self) -> None:
        assert result_excerpt("bash", "one\ntwo\n", is_error=False) == (["one", "two"], 0)

    def test_long_results_are_cut_and_counted(self) -> None:
        text = "\n".join(f"line {i}" for i in range(10))
        lines, hidden = result_excerpt("bash", text, is_error=False)
        assert lines == [f"line {i}" for i in range(6)]
        assert hidden == 4

    def test_errors_get_a_little_more_room(self) -> None:
        text = "\n".join(f"line {i}" for i in range(10))
        lines, hidden = result_excerpt("bash", text, is_error=True)
        assert len(lines) == 8
        assert hidden == 2

    def test_blank_lines_are_dropped(self) -> None:
        assert result_excerpt("bash", "a\n\n\nb\n", is_error=False) == (["a", "b"], 0)

    def test_a_successful_read_is_just_a_line_count(self) -> None:
        text = "def f():\n    pass\n"
        assert result_excerpt("read", text, is_error=False) == (["2 lines"], 0)
        assert result_excerpt("read", "only", is_error=False) == (["1 line"], 0)

    def test_a_failed_read_still_shows_the_error(self) -> None:
        assert result_excerpt("read", "File not found: x.py", is_error=True) == (["File not found: x.py"], 0)

    def test_empty_results(self) -> None:
        assert result_excerpt("bash", "", is_error=False) == ([], 0)
        assert result_excerpt("bash", "\n\n", is_error=False) == ([], 0)
