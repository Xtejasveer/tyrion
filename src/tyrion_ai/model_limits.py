"""Model context window and output token limits.

This is the single source of truth for model limits. Limits are resolved in order:

1. The user's overrides in ``~/.tyrion/models.json``, for example::

       {"llama3.1:8b": {"context_window": 8192, "max_output_tokens": 2048}}

   The key is matched against the model name exactly as typed, then against its
   canonical form (see ``canonical_name``). Either field may be left out.
2. The built-in table below.
3. ``DEFAULT_LIMITS``. Use ``is_known_model`` to tell whether this case applies.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ModelLimits:
    context_window: int
    max_output_tokens: int


# Assumed for models we know nothing about.
DEFAULT_LIMITS = ModelLimits(context_window=128_000, max_output_tokens=4_096)

OVERRIDES_FILE = Path.home() / ".tyrion" / "models.json"

# Keyed by canonical model name: lowercase, no provider prefix, no date suffix.
# Most values were checked against OpenRouter's public model list; the rest are
# noted. Local models list the model's maximum context, but a local server often
# runs with a much smaller one, so override those in models.json if needed.
_BUILTIN_LIMITS: dict[str, ModelLimits] = {
    # OpenAI
    "gpt-4o": ModelLimits(128_000, 16_384),
    "gpt-4o-mini": ModelLimits(128_000, 16_384),
    "gpt-4.5-preview": ModelLimits(128_000, 16_384),  # retired; not re-checked
    "gpt-4.1-mini": ModelLimits(1_047_576, 32_768),
    "o1": ModelLimits(200_000, 100_000),
    "o3-mini": ModelLimits(200_000, 100_000),
    # Anthropic
    "claude-3.5-sonnet": ModelLimits(200_000, 8_192),  # retired; not re-checked
    "claude-sonnet-4.5": ModelLimits(1_000_000, 64_000),
    "claude-sonnet-4-5": ModelLimits(1_000_000, 64_000),  # Anthropic's own spelling
    # Google
    "gemini-2.5-pro": ModelLimits(1_048_576, 65_536),
    "gemini-2.5-flash": ModelLimits(1_048_576, 65_536),
    # Meta
    "llama-3.3-70b-instruct": ModelLimits(131_072, 16_384),
    # DeepSeek (from DeepSeek's docs, not re-checked; deepseek-coder is an alias)
    "deepseek-chat": ModelLimits(128_000, 8_192),
    "deepseek-coder": ModelLimits(128_000, 8_192),
    # Local
    "qwen2.5-coder": ModelLimits(32_768, 4_096),
    "llama3": ModelLimits(8_192, 2_048),
}

_DATE_SUFFIX = re.compile(r"-(?:\d{4}-\d{2}-\d{2}|\d{8})$")


def canonical_name(model_name: str) -> str:
    """Reduce a model name to the form used by the built-in table.

    ``openai/gpt-4o``              -> ``gpt-4o``            (provider prefix)
    ``gpt-4o-2024-08-06``          -> ``gpt-4o``            (dated snapshot)
    ``llama3:8b``, ``model:free``  -> ``llama3``, ``model`` (tag after a colon)
    """
    name = model_name.strip().lower()
    name = name.rsplit("/", 1)[-1]
    name = name.split(":", 1)[0]
    return _DATE_SUFFIX.sub("", name)


def builtin_limits(model_name: str) -> ModelLimits | None:
    """Limits from the built-in table only (no overrides), or None if unknown."""
    return _BUILTIN_LIMITS.get(canonical_name(model_name))


# --- user overrides ---------------------------------------------------------

_OVERRIDE_FIELDS = ("context_window", "max_output_tokens")
_overrides_cache: dict[str, dict[str, int]] | None = None


def _read_overrides_file() -> dict[str, dict[str, int]]:
    try:
        raw = json.loads(OVERRIDES_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}

    overrides: dict[str, dict[str, int]] = {}
    for name, fields in raw.items():
        if not isinstance(fields, dict):
            continue
        valid = {
            key: value
            for key, value in fields.items()
            if key in _OVERRIDE_FIELDS
            and isinstance(value, int)
            and not isinstance(value, bool)
            and value > 0
        }
        if valid:
            overrides[name] = valid
    return overrides


def reload_overrides() -> None:
    """Forget the cached overrides so the file is read again on next use."""
    global _overrides_cache
    _overrides_cache = None


def _find_override(model_name: str) -> dict[str, int] | None:
    global _overrides_cache
    if _overrides_cache is None:
        _overrides_cache = _read_overrides_file()
    return _overrides_cache.get(model_name) or _overrides_cache.get(
        canonical_name(model_name)
    )


# --- public lookups ---------------------------------------------------------


def is_known_model(model_name: str) -> bool:
    """True if there is real data for this model (built-in or user override)."""
    return builtin_limits(model_name) is not None or _find_override(model_name) is not None


def get_limits(model_name: str) -> ModelLimits:
    """Resolve the limits for a model: override, then built-in, then default."""
    limits = builtin_limits(model_name) or DEFAULT_LIMITS
    override = _find_override(model_name)
    return replace(limits, **override) if override else limits


def get_context_window(model_name: str) -> int:
    """Return the context window size in tokens for a model."""
    return get_limits(model_name).context_window


def get_max_output_tokens(model_name: str) -> int:
    """Return the maximum output tokens for a model."""
    return get_limits(model_name).max_output_tokens
