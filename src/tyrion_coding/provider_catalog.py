"""Defining our known model catalog."""

from __future__ import annotations

from dataclasses import dataclass

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
    
PROVIDER_CATALOG: dict[str, ProviderMeta] = {
    "openai": ProviderMeta(
        name="OpenAI",
        adapter_type="openai_compatible",
        env_key="OPENAI_API_KEY",
        default_base_url="https://api.openai.com/v1",
        models={
            "gpt-4o": ModelMeta("gpt-4o", 128000, 4096),
            "gpt-4o-mini": ModelMeta("gpt-4o-mini", 128000, 16384),
            "gpt-4.5-preview": ModelMeta("gpt-4.5-preview", 128000, 4096),
            "o1": ModelMeta("o1", 200000, 32768),
            "o3-mini": ModelMeta("o3-mini", 200000, 100000),
            "gpt-4.1-mini": ModelMeta("gpt-4.1-mini", 1048576, 32768),
        },
    ),
    "openrouter": ProviderMeta(
        name="OpenRouter",
        adapter_type="openai_compatible",
        env_key="OPENROUTER_API_KEY",
        default_base_url="https://openrouter.ai/api/v1",
        models={
            "google/gemini-2.5-flash": ModelMeta("google/gemini-2.5-flash", 1000000, 8192),
            "google/gemini-2.5-pro": ModelMeta("google/gemini-2.5-pro", 2000000, 8192),
            "openai/gpt-4o-mini": ModelMeta("openai/gpt-4o-mini", 128000, 16384),
            "openai/gpt-4o": ModelMeta("openai/gpt-4o", 128000, 4096),
            "anthropic/claude-sonnet-4.5": ModelMeta("anthropic/claude-sonnet-4.5", 200000, 8192),
            "meta-llama/llama-3.3-70b-instruct": ModelMeta("meta-llama/llama-3.3-70b-instruct", 128000, 4096),
        },
    ),
    "deepseek": ProviderMeta(
        name="DeepSeek",
        adapter_type="openai_compatible",
        env_key="DEEPSEEK_API_KEY",
        default_base_url="https://api.deepseek.com/v1",
        models={
            "deepseek-chat": ModelMeta("deepseek-chat", 64000, 8192),
            "deepseek-coder": ModelMeta("deepseek-coder", 64000, 8192),
        },
    ),
    "local": ProviderMeta(
        name="Local",
        adapter_type="openai_compatible",
        env_key="LOCAL_API_KEY",
        default_base_url="http://localhost:11434/v1",
        models={
            "qwen2.5-coder": ModelMeta("qwen2.5-coder", 32000, 4096),
            "llama3": ModelMeta("llama3", 8192, 2048),
        },
    ),
}