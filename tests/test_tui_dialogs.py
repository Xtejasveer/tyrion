"""The two dialogs: connecting a provider and resuming a session."""

from __future__ import annotations

import io

import pytest
from rich.console import Console
from textual.app import App
from textual.widgets import Input, OptionList, Select

from tyrion_agent.messages import AssistantMessage, UserMessage
from tyrion_agent.sessions.entries import MessageEntry, SessionInfoEntry
from tyrion_coding import provider_config, session_coding
from tyrion_coding.session_coding import SessionManager
from tyrion_coding.tui.connect_modal import ConnectModal
from tyrion_coding.tui.picker import SessionPickerModal

UNSET = object()


class ModalHost(App):
    """An app that opens one dialog and records what it returned."""

    def __init__(self, modal) -> None:
        super().__init__()
        self._modal = modal
        self.result = UNSET

    def on_mount(self) -> None:
        self.push_screen(self._modal, callback=lambda result: setattr(self, "result", result))


def plain(renderable) -> str:
    console = Console(file=io.StringIO(), width=120, force_terminal=False)
    with console.capture() as capture:
        console.print(renderable)
    return capture.get()


# --- connect dialog ----------------------------------------------------------


async def test_the_api_key_is_masked_on_screen() -> None:
    app = ModalHost(ConnectModal())
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.screen.query_one("#key-input", Input).password is True


async def test_connecting_returns_the_provider_and_key() -> None:
    app = ModalHost(ConnectModal())
    async with app.run_test() as pilot:
        await pilot.pause()
        app.screen.query_one("#key-input", Input).value = "sk-or-test"

        await pilot.press("enter")
        await pilot.pause()

        assert app.result == ("openrouter", "sk-or-test")


async def test_the_chosen_provider_is_returned() -> None:
    app = ModalHost(ConnectModal())
    async with app.run_test() as pilot:
        await pilot.pause()
        app.screen.query_one("#provider-select", Select).value = "deepseek"
        app.screen.query_one("#key-input", Input).value = "sk-ds"

        await pilot.press("enter")
        await pilot.pause()

        assert app.result == ("deepseek", "sk-ds")


async def test_an_empty_key_keeps_the_dialog_open() -> None:
    app = ModalHost(ConnectModal())
    async with app.run_test() as pilot:
        await pilot.pause()

        await pilot.press("enter")
        await pilot.pause()

        assert app.result is UNSET
        assert isinstance(app.screen, ConnectModal)


async def test_escape_cancels() -> None:
    app = ModalHost(ConnectModal())
    async with app.run_test() as pilot:
        await pilot.pause()

        await pilot.press("escape")
        await pilot.pause()

        assert app.result is None


async def test_a_saved_key_is_prefilled() -> None:
    provider_config.save_credential("openrouter", "sk-saved")  # goes to a temp file in tests
    app = ModalHost(ConnectModal())
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.screen.query_one("#key-input", Input).value == "sk-saved"


# --- session picker ----------------------------------------------------------


async def _make_session(manager: SessionManager, session_id: str, *, model: str, stamp: int, messages: int) -> None:
    _, storage = manager.new_storage(session_id)
    await storage.append(
        SessionInfoEntry(id=f"{session_id}-root", session_id=session_id, model=model, timestamp=stamp)
    )
    parent = f"{session_id}-root"
    for index in range(messages):
        message = UserMessage(content=f"q{index}") if index % 2 == 0 else AssistantMessage(content=f"a{index}")
        entry = MessageEntry(id=f"{session_id}-{index}", parent_id=parent, message=message, timestamp=stamp + index)
        await storage.append(entry)
        parent = entry.id


@pytest.fixture
def sessions_dir(tmp_path, monkeypatch):
    root = tmp_path / "picker-sessions"
    monkeypatch.setattr(session_coding, "default_sessions_dir", lambda: root)
    return root


async def test_sessions_are_listed_newest_first_with_empty_ones_last(sessions_dir) -> None:
    manager = SessionManager(root=sessions_dir)
    await _make_session(manager, "aaaaaaaa1111", model="gpt-4o", stamp=1_700_000_000_000, messages=2)
    await _make_session(manager, "bbbbbbbb2222", model="google/gemini-2.5-flash", stamp=1_800_000_000_000, messages=4)
    await _make_session(manager, "cccccccc3333", model="gpt-4o", stamp=1_900_000_000_000, messages=0)  # newest, but empty

    app = ModalHost(SessionPickerModal())
    async with app.run_test() as pilot:
        await pilot.pause()
        options = app.screen.query_one("#session-list", OptionList)

        assert [option.id for option in options.options] == ["bbbbbbbb2222", "aaaaaaaa1111", "cccccccc3333"]
        rows = [plain(option.prompt) for option in options.options]
        assert "google/gemini-2.5-flash" in rows[0] and "4 messages" in rows[0] and "bbbbbbbb" in rows[0]
        assert "2 messages" in rows[1]
        assert "empty" in rows[2]


async def test_picking_a_session_returns_its_id(sessions_dir) -> None:
    manager = SessionManager(root=sessions_dir)
    await _make_session(manager, "aaaaaaaa1111", model="gpt-4o", stamp=1_700_000_000_000, messages=2)
    await _make_session(manager, "bbbbbbbb2222", model="gpt-4o", stamp=1_800_000_000_000, messages=2)

    app = ModalHost(SessionPickerModal())
    async with app.run_test() as pilot:
        await pilot.pause()

        await pilot.press("down", "enter")  # newest is first, so down = the older one
        await pilot.pause()

        assert app.result == "aaaaaaaa1111"


async def test_enter_alone_resumes_the_newest_session(sessions_dir) -> None:
    manager = SessionManager(root=sessions_dir)
    await _make_session(manager, "aaaaaaaa1111", model="gpt-4o", stamp=1_700_000_000_000, messages=2)
    await _make_session(manager, "bbbbbbbb2222", model="gpt-4o", stamp=1_800_000_000_000, messages=2)

    app = ModalHost(SessionPickerModal())
    async with app.run_test() as pilot:
        await pilot.pause()

        await pilot.press("enter")
        await pilot.pause()

        assert app.result == "bbbbbbbb2222"


async def test_escape_closes_the_picker_without_choosing(sessions_dir) -> None:
    manager = SessionManager(root=sessions_dir)
    await _make_session(manager, "aaaaaaaa1111", model="gpt-4o", stamp=1_700_000_000_000, messages=2)

    app = ModalHost(SessionPickerModal())
    async with app.run_test() as pilot:
        await pilot.pause()

        await pilot.press("escape")
        await pilot.pause()

        assert app.result is None


async def test_no_sessions_shows_a_placeholder_that_cannot_be_picked(sessions_dir) -> None:
    SessionManager(root=sessions_dir)  # creates the empty folder
    app = ModalHost(SessionPickerModal())
    async with app.run_test() as pilot:
        await pilot.pause()
        options = app.screen.query_one("#session-list", OptionList)
        assert len(options.options) == 1
        assert options.options[0].disabled
        assert "No saved sessions" in plain(options.options[0].prompt)
