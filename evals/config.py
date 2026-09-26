"""Environment Driven configuration for eval runs.

The GENERATOR (the model that actually runs tyrion on eah task) is separate 
from any future judge model. Phase 1 only needs the generator."""

from __future__ import annotations

import os 

from tyrion_agent.provider import ModelProvider
from tyrion_ai.env import OpenAICompatibleConfig
from tyrion_ai.openai_compatible import OpenAICompatibleProvider

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

DEFAULT_GENERATOR_MODEL = "deepseek/deepseek-chat"

def max_turns() -> int:
    """Hard cap on agent turns per task - protects the credit budget."""
    return int(os.environ.get("TYRION_EVAL_MAX_TURNS", "20"))

def build_generator() -> tuple[ModelProvider, str]:
    """build the Openrouter-backed provider that runs tyrion """
    api_key = os.environ.get("OPENROUTER_API_KEY")  or os.environ.get("TYRION_EVAL_API_KEY")
    if not api_key:
        raise SystemExit(
            "No API key found. Set OPENROUTER_API_KEY (or TYRION_EVAL_API_KEY)"
            "to run evals against a real model."
        )
    model = os.environ.get("TYRION_EVAL_MODEL", DEFAULT_GENERATOR_MODEL)
    config = OpenAICompatibleConfig(api_key=api_key, base_url=OPENROUTER_BASE_URL)
    return OpenAICompatibleProvider(config), model