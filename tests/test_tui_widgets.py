"""The interface pieces: messages, tool rows, status bar, thinking indicator, welcome, history."""

from __future__ import annotations

import io
import re
from contextlib import asynccontextmanager

import pytest
from rich.console import Console
from textual.app import App
from textual.widgets import Static

from tyrion_agent.messages import (
    AssistantMessage,
    TextContent,
    ToolCall,
    ToolResultMessage,
    UserMessage,
)
from tyrion_coding import theme
from tyrion_coding.tui.app import TyrionApp
from tyrion_coding.tui.welcome import WORDMARK, WelcomeHeader
from tyrion_coding.tui.widgets import (
    MessageWidget,
    PromptBox,
    ThinkingIndicator,
    ToolCallWidget,
    TUIStatusBar,
)


def plain(renderable) -> str:
    """What a Rich renderable looks like as plain text."""
    console = Console(file=io.StringIO(), width=100, force_terminal=False, theme=theme.RICH_THEME)
    with console.capture() as capture:
        console.print(renderable)
    return capture.get()


class Host(App):
    """A bare app around one widget. The widget is built inside the app, as in real use."""

    def __init__(self, factory) -> None:
        super().__init__()
        self._factory = factory
        self.widget = None

    def compose(self):
        self.widget = self._factory()
        yield self.widget


@asynccontextmanager
async def running(factory, size=(80, 24)):
    """Run `factory()`'s widget in an app. Yields (widget, pilot)."""
    app = Host(factory)
    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        yield app.widget, pilot


@asynccontextmanager
async def live():
    """An empty running app. Textual's Static widgets can only be built while one exists."""
    async with running(Static) as (_, pilot):
        yield pilot


# --- chat messages -----------------------------------------------------------


class TestMessageWidget:
    async def test_roles_become_css_classes_and_text_is_kept(self) -> None:
        async with live():
            for role in ("user", "assistant", "system", "error"):
                widget = MessageWidget(role, "hello")
                assert widget.has_class(f"role-{role}")
                assert widget.text == "hello"

    async def test_update_content_replaces_the_text(self) -> None:
        async with live():
            widget = MessageWidget("assistant", "first")
            widget.update_content("second")
            assert widget.text == "second"
            assert "second" in plain(widget.content)

    async def test_the_assistant_label_is_shown_only_when_asked(self) -> None:
        async with live():
            labelled = MessageWidget("assistant", "hi", show_label=True)
            continued = MessageWidget("assistant", "hi", show_label=False)
            assert "◆ Tyrion" in plain(labelled.content)
            assert "◆ Tyrion" not in plain(continued.content)
            assert "hi" in plain(continued.content)

    async def test_assistant_replies_are_rendered_as_markdown(self) -> None:
        async with live():
            out = plain(MessageWidget("assistant", "- one\n- two\n\n**bold**").content)
            assert "•" in out  # bullets, not raw "- "
            assert "**" not in out

    async def test_user_text_is_shown_verbatim_not_as_markup_or_markdown(self) -> None:
        async with live():
            text = "why does [/bold] fail?\n- not a list\n*not italic*"
            out = plain(MessageWidget("user", text).content)
            assert "[/bold]" in out
            assert "- not a list" in out
            assert "*not italic*" in out

    async def test_errors_get_a_marker(self) -> None:
        async with live():
            assert plain(MessageWidget("error", "API Error: 429").content).startswith("✕ API Error: 429")

    async def test_an_empty_assistant_message_does_not_crash(self) -> None:
        async with live():
            assert plain(MessageWidget("assistant", "", show_label=False).content).strip() == ""


# --- tool rows ---------------------------------------------------------------


class TestToolCallWidget:
    async def test_a_running_call_shows_a_spinner_and_what_it_acts_on(self) -> None:
        async with live():
            widget = ToolCallWidget("read", {"path": "src/app.py"})
            out = plain(widget.content)
            assert "read" in out
            assert "src/app.py" in out
            assert out[0] in "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
            assert "│" not in out  # no result yet

    async def test_the_spinner_advances(self) -> None:
        async with live():
            widget = ToolCallWidget("bash", {"command": "sleep 5"})
            first = plain(widget.content)[0]
            widget._tick()
            assert plain(widget.content)[0] != first

    async def test_a_successful_read_shows_only_a_line_count(self) -> None:
        async with live():
            widget = ToolCallWidget("read", {"path": "a.py"})
            widget.set_result("one\ntwo\nthree\n", is_error=False)
            out = plain(widget.content)
            assert out.startswith("✓ read")
            assert "3 lines" in out
            assert "two" not in out  # the file contents stay out of the transcript

    async def test_a_failed_call_shows_the_error(self) -> None:
        async with live():
            widget = ToolCallWidget("bash", {"command": "pytest"})
            widget.set_result("Command failed with exit code 1.\n\nFAILED test_x", is_error=True)
            out = plain(widget.content)
            assert out.startswith("✗ bash")
            assert "FAILED test_x" in out

    async def test_long_output_is_cut_and_the_rest_counted(self) -> None:
        async with live():
            widget = ToolCallWidget("bash", {"command": "ls"})
            widget.set_result("\n".join(f"line {i}" for i in range(10)), is_error=False)
            out = plain(widget.content)
            assert "line 5" in out
            assert "line 6" not in out
            assert "… 4 more lines" in out

    async def test_duration_is_shown_only_for_live_calls(self) -> None:
        async with live():
            just_ran = ToolCallWidget("bash", {"command": "ls"}, live=True)
            just_ran.set_result("ok", is_error=False)
            replayed = ToolCallWidget("bash", {"command": "ls"})
            replayed.set_result("ok", is_error=False)
            assert re.search(r"\d+\.\ds", plain(just_ran.content).splitlines()[0])
            assert not re.search(r"\d+\.\ds", plain(replayed.content).splitlines()[0])

    async def test_the_spinner_stops_once_a_result_arrives(self) -> None:
        async with running(lambda: ToolCallWidget("bash", {"command": "ls"}, live=True)) as (widget, _):
            assert widget._timer is not None  # animating while it runs

            widget.set_result("done", is_error=False)

            assert widget._timer is None

    async def test_a_replayed_finished_call_never_starts_animating(self) -> None:
        def finished_call() -> ToolCallWidget:
            widget = ToolCallWidget("read", {"path": "a.py"})
            widget.set_result("x", is_error=False)
            return widget

        async with running(finished_call) as (widget, _):
            assert widget._timer is None


# --- the "thinking" line -----------------------------------------------------


class TestThinkingIndicator:
    async def test_hidden_until_asked_and_animates_while_visible(self) -> None:
        async with running(ThinkingIndicator) as (indicator, pilot):
            assert not indicator.visible
            assert "Thinking" in plain(indicator.content)

            indicator.visible = True
            frame_before = indicator._frame
            await pilot.pause(0.5)

            assert indicator._frame != frame_before

    async def test_does_not_animate_while_hidden(self) -> None:
        async with running(ThinkingIndicator) as (indicator, pilot):
            await pilot.pause(0.4)
            assert indicator._frame == 0


# --- status bar --------------------------------------------------------------


def _bar(**overrides) -> TUIStatusBar:
    settings = {
        "session_id": "8fb9500034b047318c4118aa105e03e8",
        "model": "google/gemini-2.5-flash",
        "cwd": "/Users/someone/Desktop/Tyrion",
    }
    return TUIStatusBar(**{**settings, **overrides})


async def _status_line(width: int, status: str = "Idle", used: int = 41_200, limit: int = 1_048_576):
    async with running(_bar, size=(width, 4)) as (bar, pilot):
        bar.set_tokens(used, limit)
        bar.set_status(status)
        await pilot.pause()
        return bar.render()


class TestStatusBar:
    async def test_a_wide_terminal_shows_everything(self) -> None:
        line = (await _status_line(140)).plain
        for part in ("Idle", "google/gemini-2.5-flash", "41.2K / 1.0M", "8fb95000"):
            assert part in line
        assert "8fb9500034b0" not in line  # only a short session id

    @pytest.mark.parametrize("width", [120, 90, 70, 58, 44, 30, 16, 8])
    async def test_it_always_fits_and_never_cuts_a_number_in_half(self, width: int) -> None:
        line = (await _status_line(width, status="Running")).plain
        assert len(line) <= width
        assert "Running" in line or width < 12  # the state is the last thing to go
        if "/ " in line:  # if the gauge is shown, both numbers are whole
            assert "41.2K / 1.0M" in line

    async def test_detail_is_shed_in_a_sensible_order(self) -> None:
        wide = (await _status_line(120)).plain
        medium = (await _status_line(70)).plain
        narrow = (await _status_line(44)).plain
        assert "8fb95000" in wide
        assert "8fb95000" not in medium and "Desktop" not in medium and "gemini" in medium
        assert "gemini" not in narrow and "41.2K" in narrow

    async def test_the_home_folder_is_abbreviated(self, monkeypatch) -> None:
        monkeypatch.setenv("HOME", "/Users/someone")
        line = (await _status_line(140)).plain
        assert "~/Desktop/Tyrion" in line
        assert "/Users/someone" not in line

    @pytest.mark.parametrize(
        ("status", "color"),
        [("Idle", theme.SAGE), ("Error", theme.RED), ("Running", theme.GOLD), ("Compacting", theme.GOLD)],
    )
    async def test_the_state_dot_is_colored_by_state(self, status: str, color: str) -> None:
        line = await _status_line(140, status=status)
        assert str(line.spans[0].style) == color

    @pytest.mark.parametrize(
        ("used", "color"), [(10_000, theme.SAGE), (70_000, theme.AMBER), (90_000, theme.RED)]
    )
    async def test_the_gauge_turns_amber_then_red_as_the_context_fills(self, used: int, color: str) -> None:
        # "Running" has a gold dot, so sage/amber/red appear only in the gauge.
        line = await _status_line(140, status="Running", used=used, limit=100_000)
        traffic_light = {theme.SAGE, theme.AMBER, theme.RED}
        assert {str(span.style) for span in line.spans} & traffic_light == {color}

    async def test_changing_the_model_updates_the_bar(self) -> None:
        async with running(_bar, size=(140, 4)) as (bar, _):
            bar.model = "openai/gpt-4o-mini"
            assert "openai/gpt-4o-mini" in bar.render().plain

    async def test_no_known_limit_shows_a_dash(self) -> None:
        async with running(lambda: _bar(model="m"), size=(140, 4)) as (bar, _):
            assert "tokens —" in bar.render().plain


# --- welcome screen ----------------------------------------------------------


class TestWelcome:
    def test_the_wordmark_is_aligned(self) -> None:
        assert len(WORDMARK) == 6
        assert len({len(row) for row in WORDMARK}) == 1  # every row the same width

    async def test_a_big_terminal_gets_the_full_wordmark(self) -> None:
        async with running(WelcomeHeader, size=(110, 40)) as (header, _):
            out = header.render().plain
            assert "█" in out
            assert "your terminal coding agent" in out

    async def test_a_small_terminal_gets_the_compact_wordmark(self) -> None:
        async with running(WelcomeHeader, size=(60, 20)) as (header, _):
            out = header.render().plain
            assert "█" not in out
            assert "T  Y  R  I  O  N" in out


# --- the app as a whole ------------------------------------------------------


async def test_the_app_uses_the_tyrion_theme(make_session) -> None:
    app = TyrionApp(make_session())
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.theme == "tyrion"
        assert app.title == "Tyrion"
        # markdown colors reach widget content
        assert app.console.get_style("markdown.h1").color.name.lower() == theme.GOLD


async def test_the_thinking_line_sits_above_the_prompt(make_session) -> None:
    app = TyrionApp(make_session())
    async with app.run_test() as pilot:
        await pilot.pause()
        app.set_chat_active(True)
        await pilot.pause()
        assert app.query_one("#thinking").region.y < app.query_one("#prompt-box").region.y


async def test_the_prompt_footer_hint_is_only_shown_in_chat_mode(make_session) -> None:
    app = TyrionApp(make_session())
    async with app.run_test() as pilot:
        await pilot.pause()
        hint = app.query_one("#prompt-hint")
        assert not hint.display  # the welcome screen already shows the shortcuts

        app.set_chat_active(True)
        await pilot.pause()
        assert hint.display


async def test_switching_the_model_updates_the_prompt_footer(make_session) -> None:
    app = TyrionApp(make_session())
    async with app.run_test() as pilot:
        await pilot.pause()
        app.query_one(PromptBox).set_model("openai/gpt-4o-mini")
        await pilot.pause()
        assert "openai/gpt-4o-mini" in plain(app.query_one("#prompt-model-pill").content)


# --- replaying a stored conversation -----------------------------------------


async def test_history_is_shown_with_one_label_per_reply_and_tool_results_attached(make_session) -> None:
    messages = [
        UserMessage(content="fix the bug"),
        AssistantMessage(
            content=[TextContent(text="Let me look."), ToolCall(id="c1", name="read", arguments={"path": "a.py"})],
            stop_reason="toolUse",
        ),
        ToolResultMessage(tool_call_id="c1", tool_name="read", content=[TextContent(text="x\ny\n")]),
        AssistantMessage(content="Fixed it."),
        UserMessage(content="thanks"),
        AssistantMessage(content="Anytime."),
    ]
    app = TyrionApp(make_session())
    async with app.run_test() as pilot:
        await pilot.pause()
        await app.clear_transcript()

        await app.show_history(messages)
        await pilot.pause()

        rows = list(app.transcript_view.children)
        kinds = [(type(w).__name__, getattr(w, "role", "tool")) for w in rows]
        assert kinds == [
            ("MessageWidget", "user"),
            ("MessageWidget", "assistant"),
            ("ToolCallWidget", "tool"),
            ("MessageWidget", "assistant"),
            ("MessageWidget", "user"),
            ("MessageWidget", "assistant"),
        ]
        labels = [w.show_label for w in rows if getattr(w, "role", "") == "assistant"]
        assert labels == [True, False, True]  # named once per reply, not on every text block
        tool = rows[2]
        assert tool.finished and "2 lines" in plain(tool.content)
        assert app.screen.has_class("chat-active")


async def test_an_empty_history_keeps_the_welcome_screen(make_session) -> None:
    app = TyrionApp(make_session())
    async with app.run_test() as pilot:
        await pilot.pause()
        await app.show_history([])
        assert not app.screen.has_class("chat-active")
