"""Session titles: a chat is described by the first thing the user asked."""

from __future__ import annotations

from pathlib import Path

import pytest

from tyrion_agent.messages import AssistantMessage, UserMessage
from tyrion_agent.sessions.entries import (
    CompactionEntry,
    MessageEntry,
    SessionInfoEntry,
)
from tyrion_coding.display import one_line
from tyrion_coding.session_coding import SessionManager, _is_small_talk, first_prompt


def _chain(*entries):
    """Link entries into one branch: each entry's parent is the one before it."""
    linked, parent = [], None
    for entry in entries:
        entry.parent_id = parent
        parent = entry.id
        linked.append(entry)
    return linked


def _user(entry_id: str, text: str) -> MessageEntry:
    return MessageEntry(id=entry_id, message=UserMessage(content=text))


def _assistant(entry_id: str, text: str = "ok") -> MessageEntry:
    return MessageEntry(id=entry_id, message=AssistantMessage(content=text))


# --- one_line ----------------------------------------------------------------


def test_one_line_flattens_whitespace_and_newlines() -> None:
    assert one_line("fix   the bug\non the\tusers page\n\n") == "fix the bug on the users page"


def test_one_line_cuts_long_text_with_an_ellipsis() -> None:
    result = one_line("word " * 100, limit=20)
    assert len(result) == 20
    assert result.endswith("…")


def test_one_line_leaves_short_text_alone() -> None:
    assert one_line("short") == "short"
    assert one_line("   ") == ""


# --- first_prompt ------------------------------------------------------------


def test_the_title_is_the_first_user_message() -> None:
    entries = _chain(
        SessionInfoEntry(id="root", session_id="s"),
        _user("m1", "fix the pagination bug"),
        _assistant("m2"),
        _user("m3", "now add tests"),
    )
    assert first_prompt(entries) == "fix the pagination bug"


def test_a_multi_line_paste_becomes_one_line() -> None:
    entries = _chain(
        SessionInfoEntry(id="root", session_id="s"),
        _user("m1", "why does this fail?\n\nTraceback (most recent call last):\n  File x.py"),
    )
    assert first_prompt(entries) == "why does this fail? Traceback (most recent call last): File x.py"


def test_a_very_long_first_message_is_cut() -> None:
    entries = _chain(SessionInfoEntry(id="root", session_id="s"), _user("m1", "a" * 500))
    title = first_prompt(entries)
    assert title is not None and len(title) == 100 and title.endswith("…")


def test_blank_user_messages_are_skipped() -> None:
    entries = _chain(
        SessionInfoEntry(id="root", session_id="s"),
        _user("m1", "   \n  "),
        _user("m2", "the real question"),
    )
    assert first_prompt(entries) == "the real question"


def test_assistant_messages_before_the_first_prompt_are_ignored() -> None:
    entries = _chain(
        SessionInfoEntry(id="root", session_id="s"),
        _assistant("m1", "Welcome!"),
        _user("m2", "hello there"),
    )
    assert first_prompt(entries) == "hello there"


def test_a_session_where_nothing_was_asked_has_no_title() -> None:
    assert first_prompt(_chain(SessionInfoEntry(id="root", session_id="s"))) is None
    assert first_prompt([]) is None


def test_the_title_survives_a_compaction_that_replaced_the_first_messages() -> None:
    # After compaction the rebuilt transcript starts with a summary, but the log
    # still knows what the chat was originally about.
    entries = _chain(
        SessionInfoEntry(id="root", session_id="s"),
        _user("m1", "migrate the billing module to async"),
        _assistant("m2"),
        _user("m3", "next, the invoices"),
        _assistant("m4"),
        CompactionEntry(id="c1", summary="SUMMARY", replaced_entry_ids=["m1", "m2"]),
    )
    assert first_prompt(entries) == "migrate the billing module to async"


# --- small talk ---------------------------------------------------------------


@pytest.mark.parametrize(
    "greeting",
    ["hello", "Hello!", "hi", "hey there", "Say hello", "Hello Tyrion", "good morning", "thank you", "test", "ok"],
)
def test_greetings_alone_are_small_talk(greeting: str) -> None:
    assert _is_small_talk(greeting)


@pytest.mark.parametrize(
    "request_",
    [
        "fix the pagination bug",
        "hey make a calculator webpage",  # starts like a greeting but asks for something
        "test the login flow",  # "test" is a task here
        "hello world program in python",
        "hi, can you fix this bug",
        "what happened in this session",
    ],
)
def test_real_requests_are_not_small_talk(request_: str) -> None:
    assert not _is_small_talk(request_)


def test_the_title_skips_a_greeting_for_the_first_real_request() -> None:
    entries = _chain(
        SessionInfoEntry(id="root", session_id="s"),
        _user("m1", "hello"),
        _assistant("m2", "Hi! What can I do?"),
        _user("m3", "build me a calculator web app"),
    )
    assert first_prompt(entries) == "build me a calculator web app"


def test_a_chat_of_only_small_talk_still_gets_a_title() -> None:
    entries = _chain(
        SessionInfoEntry(id="root", session_id="s"),
        _user("m1", "Hello Tyrion"),
        _assistant("m2"),
        _user("m3", "thanks"),
    )
    assert first_prompt(entries) == "Hello Tyrion"


# --- through the real session files -----------------------------------------


async def test_listing_sessions_reads_titles_from_disk(tmp_path: Path) -> None:
    manager = SessionManager(root=tmp_path)
    _, storage = manager.new_storage("aaaa1111")
    for entry in _chain(
        SessionInfoEntry(id="root", session_id="aaaa1111", name=None),
        _user("m1", "explain the routing in src/api.py"),
        _assistant("m2"),
    ):
        await storage.append(entry)

    (meta,) = manager.list_sessions()

    assert meta.title == "explain the routing in src/api.py"
    assert meta.message_count == 2


async def test_an_empty_session_has_no_title(tmp_path: Path) -> None:
    manager = SessionManager(root=tmp_path)
    _, storage = manager.new_storage("bbbb2222")
    await storage.append(SessionInfoEntry(id="root", session_id="bbbb2222"))

    (meta,) = manager.list_sessions()

    assert meta.title is None
    assert meta.message_count == 0


async def test_an_explicit_session_name_is_carried_through(tmp_path: Path) -> None:
    manager = SessionManager(root=tmp_path)
    _, storage = manager.new_storage("cccc3333")
    for entry in _chain(
        SessionInfoEntry(id="root", session_id="cccc3333", name="Auth rewrite"),
        _user("m1", "fix the bug"),
    ):
        await storage.append(entry)

    (meta,) = manager.list_sessions()

    assert meta.name == "Auth rewrite"  # the picker prefers this over the derived title
    assert meta.title == "fix the bug"
