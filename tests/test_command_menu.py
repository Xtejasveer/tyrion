"""Slash-command list: opens on `/`, filters as you type, arrows + Enter run a command."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from tyrion_ai.fake import FakeProvider
from tyrion_coding.commands import SlashCommand, registry
from tyrion_coding.session import CodingSession
from tyrion_coding.session_coding import SessionManager
from tyrion_coding.tui.app import TyrionApp
from tyrion_coding.tui.widgets import CommandMenu, MessageWidget, PromptInput

DEFAULT_COMMANDS = [
    "/help", "/clear", "/quit", "/exit", "/model", "/resume", "/compact", "/connect",
]  # fmt: skip


class RecordingApp(TyrionApp):
    """The real app, except a submitted prompt is only recorded, not acted on."""

    def __init__(self, session: CodingSession) -> None:
        super().__init__(session=session)
        self.submitted: list[str] = []

    async def on_prompt_input_submitted(self, event: PromptInput.Submitted) -> None:
        event.prevent_default()  # don't also run the real handler
        self.submitted.append(event.text)


def _session(tmp_path: Path) -> CodingSession:
    _, storage = SessionManager(root=tmp_path).new_storage()
    provider = FakeProvider([])
    provider._config = SimpleNamespace(api_key="test-key")  # no connect dialog
    return CodingSession(
        cwd=tmp_path, provider=provider, model="gpt-4o", system="test",
        storage=storage, tools=[],
    )  # fmt: skip


async def _type(pilot, text: str) -> None:
    keys = ["slash" if ch == "/" else "space" if ch == " " else ch for ch in text]
    await pilot.press(*keys)
    await pilot.pause()


async def _press(pilot, *keys: str) -> None:
    await pilot.press(*keys)
    await pilot.pause()


def _names(menu: CommandMenu) -> list[str]:
    return [command.name for command in menu.matches]


@pytest.fixture
def extra_commands(monkeypatch):
    """Register throwaway commands that record how they were run."""
    calls: list[tuple[str, list[str]]] = []

    def add(name: str) -> None:
        async def handler(app, args, _name=name):
            calls.append((_name, args))

        monkeypatch.setitem(registry._commands, name, SlashCommand(name, f"test {name}", handler))

    for name in ("/ping", "/pong", "/echo"):
        add(name)
    return calls


# --- filtering (no UI) -------------------------------------------------------


def test_registry_matching_filters_by_prefix_in_registration_order() -> None:
    assert [c.name for c in registry.matching("/")] == DEFAULT_COMMANDS
    assert [c.name for c in registry.matching("/co")] == ["/compact", "/connect"]
    assert [c.name for c in registry.matching("/MO")] == ["/model"]  # case-insensitive
    assert registry.matching("/zzz") == []


# --- opening, filtering, closing ---------------------------------------------


@pytest.mark.asyncio
async def test_list_is_hidden_until_a_slash_is_typed(tmp_path: Path) -> None:
    app = RecordingApp(_session(tmp_path))
    async with app.run_test() as pilot:
        menu = app.query_one(CommandMenu)
        assert not menu.display

        await _type(pilot, "hello")
        assert not menu.display


@pytest.mark.asyncio
async def test_typing_a_slash_lists_every_command_with_the_first_selected(tmp_path: Path) -> None:
    app = RecordingApp(_session(tmp_path))
    async with app.run_test() as pilot:
        menu = app.query_one(CommandMenu)

        await _type(pilot, "/")

        assert menu.display
        assert _names(menu) == DEFAULT_COMMANDS
        assert menu.selected_command.name == "/help"
        shown = menu.render().plain
        assert "/connect" in shown
        assert "List available commands" in shown  # descriptions are shown too


@pytest.mark.asyncio
async def test_the_list_narrows_as_you_type_and_closes_when_nothing_matches(tmp_path: Path) -> None:
    app = RecordingApp(_session(tmp_path))
    async with app.run_test() as pilot:
        menu = app.query_one(CommandMenu)

        await _type(pilot, "/co")
        assert _names(menu) == ["/compact", "/connect"]

        await _type(pilot, "n")
        assert _names(menu) == ["/connect"]

        await _type(pilot, "x")  # "/conx" matches nothing
        assert not menu.display


@pytest.mark.asyncio
async def test_the_list_closes_once_you_start_typing_arguments(tmp_path: Path) -> None:
    app = RecordingApp(_session(tmp_path))
    async with app.run_test() as pilot:
        menu = app.query_one(CommandMenu)

        await _type(pilot, "/model")
        assert menu.display

        await _type(pilot, " gpt-4o")
        assert not menu.display


@pytest.mark.asyncio
async def test_deleting_the_slash_closes_the_list(tmp_path: Path) -> None:
    app = RecordingApp(_session(tmp_path))
    async with app.run_test() as pilot:
        menu = app.query_one(CommandMenu)
        await _type(pilot, "/")
        assert menu.display

        await _press(pilot, "backspace")

        assert not menu.display


# --- arrow keys --------------------------------------------------------------


@pytest.mark.asyncio
async def test_arrow_keys_move_the_highlight_and_wrap_around(tmp_path: Path) -> None:
    app = RecordingApp(_session(tmp_path))
    async with app.run_test() as pilot:
        menu = app.query_one(CommandMenu)
        await _type(pilot, "/")

        await _press(pilot, "down", "down")
        assert menu.selected_command.name == "/quit"

        await _press(pilot, "up")
        assert menu.selected_command.name == "/clear"

        await _press(pilot, "up", "up")  # past the top: wraps to the last command
        assert menu.selected_command.name == "/connect"

        await _press(pilot, "down")  # past the bottom: wraps to the first
        assert menu.selected_command.name == "/help"


@pytest.mark.asyncio
async def test_arrow_keys_do_not_change_the_typed_text(tmp_path: Path) -> None:
    app = RecordingApp(_session(tmp_path))
    async with app.run_test() as pilot:
        await _type(pilot, "/co")

        await _press(pilot, "down", "up")

        assert app.query_one(PromptInput).text == "/co"


@pytest.mark.asyncio
async def test_a_long_list_scrolls_to_keep_the_highlight_visible(tmp_path: Path, monkeypatch) -> None:
    async def handler(app, args):
        pass

    for i in range(12):
        name = f"/x{i:02}"
        monkeypatch.setitem(registry._commands, name, SlashCommand(name, "many", handler))

    app = RecordingApp(_session(tmp_path))
    async with app.run_test() as pilot:
        menu = app.query_one(CommandMenu)
        await _type(pilot, "/x")
        shown = menu.render().plain
        assert "/x00" in shown
        assert "/x11" not in shown  # only MAX_ROWS rows at a time

        await _press(pilot, "up")  # wraps to the last one
        shown = menu.render().plain
        assert menu.selected_command.name == "/x11"
        assert "/x11" in shown
        assert "/x00" not in shown


# --- Enter runs the highlighted command --------------------------------------


@pytest.mark.asyncio
async def test_enter_submits_the_highlighted_command_not_the_typed_prefix(tmp_path: Path) -> None:
    app = RecordingApp(_session(tmp_path))
    async with app.run_test() as pilot:
        await _type(pilot, "/mo")

        await _press(pilot, "enter")

        assert app.submitted == ["/model"]
        assert app.query_one(PromptInput).text == ""
        assert not app.query_one(CommandMenu).display


@pytest.mark.asyncio
async def test_enter_on_a_bare_slash_runs_the_first_command(tmp_path: Path) -> None:
    app = RecordingApp(_session(tmp_path))
    async with app.run_test() as pilot:
        await _type(pilot, "/")

        await _press(pilot, "enter")

        assert app.submitted == ["/help"]  # a harmless default


@pytest.mark.asyncio
async def test_enter_runs_the_command_picked_with_the_arrow_keys(tmp_path: Path) -> None:
    app = RecordingApp(_session(tmp_path))
    async with app.run_test() as pilot:
        await _type(pilot, "/")
        await _press(pilot, "down", "down", "down")  # help -> clear -> quit -> exit

        await _press(pilot, "enter")

        assert app.submitted == ["/exit"]


@pytest.mark.asyncio
async def test_the_chosen_command_really_runs(tmp_path: Path, extra_commands) -> None:
    app = TyrionApp(session=_session(tmp_path))
    async with app.run_test() as pilot:
        await _type(pilot, "/p")  # matches /ping and /pong
        await _press(pilot, "down", "enter")

        assert extra_commands == [("/pong", [])]


@pytest.mark.asyncio
async def test_a_command_with_arguments_is_submitted_as_typed(tmp_path: Path, extra_commands) -> None:
    app = TyrionApp(session=_session(tmp_path))
    async with app.run_test() as pilot:
        await _type(pilot, "/echo hi there")
        assert not app.query_one(CommandMenu).display

        await _press(pilot, "enter")

        assert extra_commands == [("/echo", ["hi", "there"])]


@pytest.mark.asyncio
async def test_an_unknown_command_still_reports_unknown(tmp_path: Path) -> None:
    app = TyrionApp(session=_session(tmp_path))
    async with app.run_test() as pilot:
        await _type(pilot, "/zzz")
        assert not app.query_one(CommandMenu).display

        await _press(pilot, "enter")

        texts = [w.text for w in app.query(MessageWidget)]
        assert any("Unknown command" in text for text in texts)


@pytest.mark.asyncio
async def test_a_normal_prompt_is_unaffected(tmp_path: Path) -> None:
    app = RecordingApp(_session(tmp_path))
    async with app.run_test() as pilot:
        await _type(pilot, "fix the bug")

        await _press(pilot, "enter")

        assert app.submitted == ["fix the bug"]


# --- Tab and Escape ----------------------------------------------------------


@pytest.mark.asyncio
async def test_tab_fills_in_the_highlighted_command_without_running_it(tmp_path: Path) -> None:
    app = RecordingApp(_session(tmp_path))
    async with app.run_test() as pilot:
        await _type(pilot, "/co")
        await _press(pilot, "down")  # /connect

        await _press(pilot, "tab")

        assert app.query_one(PromptInput).text == "/connect "  # ready for arguments
        assert app.submitted == []
        assert not app.query_one(CommandMenu).display


@pytest.mark.asyncio
async def test_escape_closes_the_list_first_and_only_then_cancels_a_run(tmp_path: Path) -> None:
    app = RecordingApp(_session(tmp_path))
    cancels: list[int] = []
    app.action_cancel_run = lambda: cancels.append(1)  # what Escape is bound to
    async with app.run_test() as pilot:
        menu = app.query_one(CommandMenu)
        await _type(pilot, "/mo")

        await _press(pilot, "escape")
        assert not menu.display
        assert app.query_one(PromptInput).text == "/mo"  # the text is kept
        assert cancels == []  # this Escape belonged to the list

        await _press(pilot, "escape")  # nothing open now: normal behavior
        assert cancels == [1]


# --- layout ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_opening_the_list_keeps_the_newest_messages_in_view(tmp_path: Path) -> None:
    app = RecordingApp(_session(tmp_path))
    async with app.run_test(size=(100, 30)) as pilot:
        app.set_chat_active(True)
        for i in range(25):
            await app.transcript_view.mount(MessageWidget("user", f"message {i}"))
        await pilot.pause()
        app.transcript_view.scroll_end(animate=False)
        await pilot.pause()
        transcript = app.transcript_view
        assert transcript.scroll_y >= transcript.max_scroll_y - 1

        await _type(pilot, "/")  # the list takes room from the transcript
        await pilot.pause()

        assert transcript.scroll_y >= transcript.max_scroll_y - 1


@pytest.mark.asyncio
async def test_opening_the_list_does_not_yank_a_transcript_the_user_scrolled_up(tmp_path: Path) -> None:
    app = RecordingApp(_session(tmp_path))
    async with app.run_test(size=(100, 30)) as pilot:
        app.set_chat_active(True)
        for i in range(25):
            await app.transcript_view.mount(MessageWidget("user", f"message {i}"))
        await pilot.pause()
        transcript = app.transcript_view
        transcript.scroll_to(y=0, animate=False)
        await pilot.pause()

        await _type(pilot, "/")
        await pilot.pause()

        assert transcript.scroll_y == 0
