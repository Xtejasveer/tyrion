"""Shared HTTP client for provider API calls."""

from __future__ import annotations

import httpx

def create_http_client(
        *,
        base_url:str,
        api_key:str,
        timeout_seconds: int = 120,
) -> httpx.AsyncClient:
    """Create an async HTTP client configured for an LLM API."""
    return httpx.AsyncClient(
        base_url= base_url,
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type" : "application/json",
        },
        timeout = httpx.Timeout(timeout_seconds, connect= 10.0)
    )