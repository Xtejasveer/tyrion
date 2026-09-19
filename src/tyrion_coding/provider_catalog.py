"""Defining our known model catalog."""

from __future__ import annotations

from dataclasses import dataclass

from tyrion_ai.model_limits import DEFAULT_LIMITS, builtin_limits

@dataclass(frozen=True, slots=True)
class ModelMeta:
    name:str
    context_window: int
    max_output_tokens: int

@dataclass(frozen=True, slots=True)
class ProviderMeta:
    name: str
    adapter_type: str
    env_key: str
    default_base_url: str
    models: dict[str, ModelMeta]


def _models(*names: str) -> dict[str, ModelMeta]:
    """Catalog entries whose limits come from tyrion_ai.model_limits (the one table)."""
    entries: dict[str, ModelMeta] = {}
    for name in names:
        limits = builtin_limits(name) or DEFAULT_LIMITS
        entries[name] = ModelMeta(name, limits.context_window, limits.max_output_tokens)
    return entries


PROVIDER_CATALOG: dict[str, ProviderMeta] = {
    "openai": ProviderMeta(
        name="OpenAI",
        adapter_type="openai_compatible",
        env_key="OPENAI_API_KEY",
        default_base_url="https://api.openai.com/v1",
        models=_models(
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-4.5-preview",
            "o1",
            "o3-mini",
            "gpt-4.1-mini",
        ),
    ),
    "openrouter": ProviderMeta(
        name="OpenRouter",
        adapter_type="openai_compatible",
        env_key="OPENROUTER_API_KEY",
        default_base_url="https://openrouter.ai/api/v1",
        models=_models(
            "google/gemini-2.5-flash",
            "google/gemini-2.5-pro",
            "openai/gpt-4o-mini",
            "openai/gpt-4o",
            "anthropic/claude-sonnet-4.5",
            "meta-llama/llama-3.3-70b-instruct",
        ),
    ),
    "deepseek": ProviderMeta(
        name="DeepSeek",
        adapter_type="openai_compatible",
        env_key="DEEPSEEK_API_KEY",
        default_base_url="https://api.deepseek.com/v1",
        models=_models("deepseek-chat", "deepseek-coder"),
    ),
    "local": ProviderMeta(
        name="Local",
        adapter_type="openai_compatible",
        env_key="LOCAL_API_KEY",
        default_base_url="http://localhost:11434/v1",
        models=_models("qwen2.5-coder", "llama3"),
    ),
}
