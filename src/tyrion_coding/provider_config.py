from __future__ import annotations

import json
import os
from pathlib import Path

from tyrion_ai.env import OpenAICompatibleConfig
from tyrion_ai.model_limits import get_limits
from tyrion_ai.openai_compatible import OpenAICompatibleProvider
from tyrion_coding.provider_catalog import (
    PROVIDER_CATALOG,
    ModelMeta,
    ProviderMeta,
)

CREDENTIALS_FILE = Path.home() / ".tyrion" / "credentials.json"


def load_saved_credentials() -> dict[str, str]:
    """Load saved API keys from disk."""
    if not CREDENTIALS_FILE.exists():
        return {}
    try:
        with open(CREDENTIALS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _write_private(path: Path, text: str) -> None:
    """Write `text` to `path` so that only the current user can read it.

    Permissions are set on the open file *before* the secret goes in, so there is
    no moment when others can read it. A file created loosely by an older
    version is tightened too.
    """
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        os.fchmod(handle.fileno(), 0o600)
        handle.write(text)


def save_credential(provider_name: str, api_key: str) -> None:
    """Save an API key for a provider to disk (readable only by you)."""
    CREDENTIALS_FILE.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    creds = load_saved_credentials()
    creds[provider_name.lower()] = api_key
    try:
        _write_private(CREDENTIALS_FILE, json.dumps(creds, indent=2))
    except OSError:
        pass


def resolve_model_and_provider(model_name: str) -> tuple[ProviderMeta, ModelMeta]:
    """Finds the provider and model meta matching the target model name."""
    for provider in PROVIDER_CATALOG.values():
        if model_name in provider.models:
            return provider, provider.models[model_name]

    # Fallback to OpenAI if not mapped
    openai_prov = PROVIDER_CATALOG["openai"]
    limits = get_limits(model_name)
    fallback_model = ModelMeta(model_name, limits.context_window, limits.max_output_tokens)
    return openai_prov, fallback_model


def get_provider_for_model(
    model_name: str,
    allow_unauthenticated: bool = False,
) -> tuple[OpenAICompatibleProvider, ProviderMeta, ModelMeta]:
    """Dynamically resolves environment variables, saved credentials, and base URLs."""
    saved_creds = load_saved_credentials()

    # If the user ran with default model but only has openrouter credentials, auto-route to openrouter
    if model_name in ("gpt-4.1-mini", "default"):
        if not os.environ.get("OPENAI_API_KEY") and not saved_creds.get("openai"):
            if "openrouter" in saved_creds or os.environ.get("OPENROUTER_API_KEY"):
                model_name = "google/gemini-2.5-flash"

    provider_meta, model_meta = resolve_model_and_provider(model_name)

    # 1. Resolve API Key: check environment first, then saved credentials
    env_key = provider_meta.env_key
    api_key = os.environ.get(env_key, "")

    if not api_key:
        api_key = saved_creds.get(provider_meta.name.lower(), "")

    if not api_key:
        api_key = os.environ.get("OPENAI_API_KEY", "")

    # Fallback to OpenRouter if user has an OpenRouter key configured
    if not api_key and provider_meta.name != "Local":
        if "openrouter" in saved_creds or os.environ.get("OPENROUTER_API_KEY"):
            openrouter_key = os.environ.get("OPENROUTER_API_KEY") or saved_creds.get("openrouter", "")
            openrouter_prov = PROVIDER_CATALOG["openrouter"]
            if model_name in openrouter_prov.models:
                provider_meta = openrouter_prov
                model_meta = openrouter_prov.models[model_name]
                api_key = openrouter_key
            elif f"openai/{model_name}" in openrouter_prov.models:
                provider_meta = openrouter_prov
                model_meta = openrouter_prov.models[f"openai/{model_name}"]
                api_key = openrouter_key
            else:
                provider_meta = openrouter_prov
                model_meta = openrouter_prov.models["google/gemini-2.5-flash"]
                api_key = openrouter_key

    # Local Ollama/vLLM endpoints do not require keys
    if not api_key and provider_meta.name != "Local":
        if allow_unauthenticated:
            api_key = "unauthenticated"
        else:
            raise ValueError(
                f"API key required. Please set {env_key} or connect via /connect in the UI."
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
        api_key=api_key,
        base_url=base_url,
    )
    return OpenAICompatibleProvider(config), provider_meta, model_meta


def connect_provider(
    provider_name: str,
    api_key: str,
) -> tuple[OpenAICompatibleProvider, str]:
    """Connect a provider by saving credentials and building an active client."""
    save_credential(provider_name, api_key)

    matched_meta = PROVIDER_CATALOG.get(provider_name.lower())
    if matched_meta is None:
        matched_meta = PROVIDER_CATALOG["openrouter"]

    # Also update current process environment variables
    os.environ[matched_meta.env_key] = api_key
    if provider_name.lower() == "openrouter":
        os.environ["OPENROUTER_API_KEY"] = api_key
    elif provider_name.lower() == "openai":
        os.environ["OPENAI_API_KEY"] = api_key

    config = OpenAICompatibleConfig(
        api_key=api_key,
        base_url=matched_meta.default_base_url,
    )

    # Choose a default model from this provider
    default_model = next(iter(matched_meta.models.keys()))
    return OpenAICompatibleProvider(config), default_model