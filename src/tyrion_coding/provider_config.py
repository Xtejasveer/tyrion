from __future__ import annotations

import os
from tyrion_ai.env import OpenAICompatibleConfig
from tyrion_ai.openai_compatible import OpenAICompatibleProvider
from tyrion_coding.provider_catalog import (
    PROVIDER_CATALOG,
    ModelMeta,
    ProviderMeta,
)

def resolve_model_and_provider(model_name: str) -> tuple[ProviderMeta, ModelMeta]:
    """Finds the provider and model mets matching the target model name"""
    for provider in PROVIDER_CATALOG.values():
        if model_name in provider.models:
            return provider, provider.models[model_name]

    #Fallback to OpenAI if not mapped in registry
    openai_prov = PROVIDER_CATALOG["openai"]
    fallback_model = ModelMeta(model_name, 128000, 4096)
    return openai_prov, fallback_model

def get_provider_for_model(
        model_name: str,
) -> tuple[OpenAICompatibleProvider, ProviderMeta, ModelMeta]:
    """Dynamically resolves environment variables and base URLs and instantiates client."""

    provider_meta, model_meta = resolve_model_and_provider(model_name)

    # 1. Resolve API key
    env_key = provider_meta.env_key
    api_key = os.environ.get(env_key, "")

    if not api_key:
        api_key = os.environ.get("OPENAI_API_KEY", "")

    if not api_key and provider_meta.name != "Local":
        raise ValueError(
            f"API key required. Please set {env_key} or OPENAI_API_KEY environment variable."
        )
    elif not api_key:
        api_key = "dummy-key"

    # 2. Resolve Base URL
    prefix = provider_meta.name.upper()
    base_url = os.environ.get(f"{prefix}_BASE_URL", "")
    if not base_url:
        base_url = os.environ.get("OPENAI_BASE_URL", "")
    if not base_url:
        base_url = provider_meta.default_base_url

    config = OpenAICompatibleConfig(
        api_key = api_key,
        base_url=base_url,
    )
    return OpenAICompatibleProvider(config), provider_meta, model_meta


