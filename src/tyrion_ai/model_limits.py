"""Model context window and output token limits."""

from __future__ import annotations

# Self-contained limits mapping inside tyrion_ai (context_window, max_output_tokens)
MODEL_LIMITS: dict[str, tuple[int, int]] = {
    "gpt-4o": (128000, 4096),
    "gpt-4o-mini": (128000, 16384),
    "gpt-4.5-preview": (128000, 4096),
    "o1": (200000, 32768),
    "o3-mini": (200000, 100000),
    "gpt-4.1-mini": (1048576, 32768),
    "anthropic/claude-3.5-sonnet": (200000, 8192),
    "google/gemini-2.5-pro": (2000000, 8192),
    "google/gemini-2.5-flash": (1000000, 8192),
    "meta-llama/llama-3.3-70b-instruct": (128000, 4096),
    "deepseek-chat": (64000, 8192),
    "deepseek-coder": (64000, 8192),
    "qwen2.5-coder": (32000, 4096),
    "llama3": (8192, 2048),
}

def get_context_window(model_name: str) -> int:
    """Return the context window size in tokens for a model."""
    return MODEL_LIMITS.get(model_name, (128000, 4096))[0]

def get_max_output_tokens(model_name: str) -> int:
    """Return the maximum output tokens for a model."""
    return MODEL_LIMITS.get(model_name, (128000, 4096))[1]