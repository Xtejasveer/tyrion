"""Saved API keys: stored where only the current user can read them."""

from __future__ import annotations

import stat
from pathlib import Path

from tyrion_coding import provider_config
from tyrion_coding.provider_config import load_saved_credentials, save_credential


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_a_saved_key_is_readable_only_by_its_owner() -> None:
    save_credential("openrouter", "sk-secret")

    assert _mode(provider_config.CREDENTIALS_FILE) == 0o600


def test_the_key_round_trips() -> None:
    save_credential("OpenRouter", "sk-one")  # provider names are case-insensitive
    save_credential("deepseek", "sk-two")

    assert load_saved_credentials() == {"openrouter": "sk-one", "deepseek": "sk-two"}


def test_saving_again_replaces_the_key_and_keeps_the_others() -> None:
    save_credential("openrouter", "old")
    save_credential("openai", "keep-me")
    save_credential("openrouter", "new")

    assert load_saved_credentials() == {"openrouter": "new", "openai": "keep-me"}


def test_a_file_an_older_version_left_world_readable_is_tightened() -> None:
    path = provider_config.CREDENTIALS_FILE
    path.write_text('{"openai": "sk-old"}', encoding="utf-8")
    path.chmod(0o644)  # what earlier versions created

    save_credential("openrouter", "sk-new")

    assert _mode(path) == 0o600
    assert load_saved_credentials() == {"openai": "sk-old", "openrouter": "sk-new"}


def test_a_new_config_folder_is_private(tmp_path, monkeypatch) -> None:
    file = tmp_path / "fresh-home" / ".tyrion" / "credentials.json"
    monkeypatch.setattr(provider_config, "CREDENTIALS_FILE", file)

    save_credential("openrouter", "sk-secret")

    assert _mode(file.parent) == 0o700
    assert _mode(file) == 0o600
