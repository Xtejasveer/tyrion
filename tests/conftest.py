from __future__ import annotations

import pytest

from tyrion_ai import model_limits


@pytest.fixture(autouse=True)
def _isolate_model_overrides(tmp_path, monkeypatch):
    """Never read the developer's real ~/.tyrion/models.json during tests."""
    monkeypatch.setattr(model_limits, "OVERRIDES_FILE", tmp_path / "models.json")
    model_limits.reload_overrides()
    yield
    model_limits.reload_overrides()
