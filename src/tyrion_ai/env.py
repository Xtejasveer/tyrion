"""Environment-based provider coonfiguration."""

from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_TIMEOUT_SECONDS = 120
DEFAULT_MAX_RETRIES = 3

@dataclass(frozen=True, slots= True)
class OpenAICompatibleConfig:
    """Configuration for an OpenAI endpoint."""

    api_key : str
    base_url : str = DEFAULT_OPENAI_BASE_URL
    timeout_seconds : int = DEFAULT_TIMEOUT_SECONDS
    max_retries: int = DEFAULT_MAX_RETRIES

def openai_compatible_config_from_env() -> OpenAICompatibleConfig:
    """Load OpenAI configuration from envirenment variables.
    Reads:
        OPENAI_API_KEY - Required. Your API key.
        OPENAI_BASE_URL - Optional. Deafults to https://api.openai.com/v1
    
    """
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise ValueError(
            "OPENAI_API_KEY envirenment variable is required."
            "Get one at https://platform.openai.com/api-keys"
        )
    base_url = os.environ.get("OPENAI_BASE_URL", DEFAULT_OPENAI_BASE_URL)

    return OpenAICompatibleConfig(api_key=api_key, base_url= base_url)

    