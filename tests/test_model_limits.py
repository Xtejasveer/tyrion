"""Model limits: name matching, the built-in table, user overrides, one source of truth."""

from __future__ import annotations

import json

import pytest

from tyrion_ai import model_limits
from tyrion_ai.model_limits import (
    DEFAULT_LIMITS,
    builtin_limits,
    canonical_name,
    get_context_window,
    get_limits,
    get_max_output_tokens,
    is_known_model,
    reload_overrides,
)
from tyrion_coding.context_window import unknown_model_notice
from tyrion_coding.provider_catalog import PROVIDER_CATALOG


def _write_overrides(data: object) -> None:
    model_limits.OVERRIDES_FILE.write_text(json.dumps(data), encoding="utf-8")
    reload_overrides()


# --- name matching -----------------------------------------------------------


@pytest.mark.parametrize(
    ("typed", "canonical"),
    [
        ("gpt-4o", "gpt-4o"),
        ("openai/gpt-4o", "gpt-4o"),  # provider prefix
        ("OpenAI/GPT-4o", "gpt-4o"),  # case
        ("gpt-4o-2024-08-06", "gpt-4o"),  # dated snapshot
        ("claude-sonnet-4-5-20250929", "claude-sonnet-4-5"),  # compact date
        ("llama3:8b", "llama3"),  # Ollama tag
        ("deepseek/deepseek-chat:free", "deepseek-chat"),  # prefix + tag
    ],
)
def test_canonical_name(typed: str, canonical: str) -> None:
    assert canonical_name(typed) == canonical


def test_name_variants_resolve_to_the_same_limits() -> None:
    expected = get_limits("gpt-4o")
    for variant in ("openai/gpt-4o", "gpt-4o-2024-08-06", "GPT-4o"):
        assert get_limits(variant) == expected
        assert is_known_model(variant)


def test_ollama_tag_resolves_to_the_base_model() -> None:
    assert get_context_window("llama3:8b") == get_context_window("llama3") == 8_192


# --- unknown models ----------------------------------------------------------


def test_unknown_model_gets_the_default_and_is_reported_unknown() -> None:
    assert not is_known_model("some-new-model")
    assert get_limits("some-new-model") == DEFAULT_LIMITS


def test_unknown_model_notice_only_appears_for_unknown_models() -> None:
    assert unknown_model_notice("gpt-4o") is None

    notice = unknown_model_notice("some-new-model")
    assert notice is not None
    assert "some-new-model" in notice
    assert "128,000" in notice
    assert "models.json" in notice


# --- corrected values --------------------------------------------------------


def test_gemini_pro_is_about_one_million_tokens_not_two() -> None:
    assert get_context_window("google/gemini-2.5-pro") == 1_048_576


def test_gpt4o_output_limit() -> None:
    assert get_max_output_tokens("gpt-4o") == 16_384


# --- user overrides ----------------------------------------------------------


def test_override_replaces_the_default_for_an_unknown_model() -> None:
    _write_overrides({"llama3.1:8b": {"context_window": 8_192, "max_output_tokens": 2_048}})

    assert is_known_model("llama3.1:8b")
    assert get_limits("llama3.1:8b").context_window == 8_192
    assert get_limits("llama3.1:8b").max_output_tokens == 2_048
    assert unknown_model_notice("llama3.1:8b") is None
    # The override is for that exact tag: other tags of the model are unaffected.
    assert not is_known_model("llama3.1:70b")


def test_override_can_change_just_one_field_of_a_known_model() -> None:
    builtin = get_limits("gpt-4o")
    _write_overrides({"gpt-4o": {"context_window": 50_000}})

    limits = get_limits("gpt-4o")
    assert limits.context_window == 50_000
    assert limits.max_output_tokens == builtin.max_output_tokens


def test_override_under_the_canonical_name_covers_all_variants() -> None:
    _write_overrides({"llama3.1": {"context_window": 16_000}})

    assert get_context_window("llama3.1:8b") == 16_000
    assert get_context_window("llama3.1:70b") == 16_000


def test_invalid_overrides_are_ignored() -> None:
    _write_overrides(
        {
            "a": {"context_window": "big"},
            "b": {"context_window": -5},
            "c": {"context_window": True},
            "d": "not an object",
            "e": {"unknown_field": 1},
        }
    )

    for name in "abcde":
        assert not is_known_model(name)


def test_malformed_overrides_file_is_ignored() -> None:
    model_limits.OVERRIDES_FILE.write_text("{ not json", encoding="utf-8")
    reload_overrides()

    assert get_limits("gpt-4o") == builtin_limits("gpt-4o")


# --- one source of truth -----------------------------------------------------


def test_every_catalog_model_is_in_the_builtin_table_with_the_same_numbers() -> None:
    for provider in PROVIDER_CATALOG.values():
        for name, meta in provider.models.items():
            limits = builtin_limits(name)
            assert limits is not None, f"{name} is in the catalog but not in model_limits"
            assert meta.context_window == limits.context_window
            assert meta.max_output_tokens == limits.max_output_tokens
