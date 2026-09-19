from __future__ import annotations

from types import SimpleNamespace

import pytest

from tyrion_ai import model_limits
from tyrion_ai.fake import FakeProvider
from tyrion_coding import provider_config
from tyrion_coding.session import CodingSession
from tyrion_coding.session_coding import SessionManager


@pytest.fixture(autouse=True)
def _isolate_model_overrides(tmp_path, monkeypatch):
    """Never read the developer's real ~/.tyrion/models.json during tests."""
    monkeypatch.setattr(model_limits, "OVERRIDES_FILE", tmp_path / "models.json")
    model_limits.reload_overrides()
    yield
    model_limits.reload_overrides()


@pytest.fixture(autouse=True)
def _isolate_credentials(tmp_path, monkeypatch):
    """Never read (or write) the developer's real saved API keys during tests."""
    monkeypatch.setattr(provider_config, "CREDENTIALS_FILE", tmp_path / "credentials.json")


@pytest.fixture
def make_session(tmp_path):
    """Build a CodingSession backed by a fake provider, storing under tmp_path."""

    def make(model: str = "gpt-4o") -> CodingSession:
        _, storage = SessionManager(root=tmp_path / "sessions").new_storage()
        provider = FakeProvider([])
        provider._config = SimpleNamespace(api_key="test-key")  # so no connect dialog opens
        return CodingSession(
            cwd=tmp_path, provider=provider, model=model, system="test",
            storage=storage, tools=[],
        )  # fmt: skip

    return make
