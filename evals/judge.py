"""An OpenRouter-backed judge for DeepEval's LLM-as-a-judge metrics.

DeepEval's built-in metrics hardcode api.openai.com. This wraps an
OpenAI-compatible OpenRouter endpoint in DeepEval's DeepEvalBaseLLM interface,
so the judged metrics route through your OpenRouter credits instead.

Judge-model-agnostic: set TYRION_JUDGE_MODEL (default: openai/gpt-4o-mini).
Keep the judge a different model family than the generator (TYRION_EVAL_MODEL)
to avoid self-preference bias.
"""

from __future__ import annotations

import json
import os
from typing import Any

from deepeval.models.base_model import DeepEvalBaseLLM

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_JUDGE_MODEL = "openai/gpt-4o-mini"

_JUDGE_SYSTEM = (
    "You are a strict, fair evaluation judge. Follow the instructions exactly "
    "and base your judgement only on the evidence provided."
)


def _extract_json_block(text: str) -> str:
    """Best-effort pull of a JSON object out of a model reply."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("```", 2)[1]
        if t.lower().startswith("json"):
            t = t[4:]
        t = t.strip().strip("`").strip()
    start, end = t.find("{"), t.rfind("}")
    if start != -1 and end > start:
        return t[start : end + 1]
    return t


class OpenRouterJudge(DeepEvalBaseLLM):
    def __init__(self, model: str | None = None) -> None:
        self._model_name = model or os.environ.get(
            "TYRION_JUDGE_MODEL", DEFAULT_JUDGE_MODEL
        )
        api_key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get(
            "TYRION_EVAL_API_KEY"
        )
        if not api_key:
            raise SystemExit(
                "No API key found for the judge. Set OPENROUTER_API_KEY."
            )
        self._api_key = api_key
        self._async_client = None
        super().__init__(self._model_name)  # sets self.model via load_model()

    # --- DeepEvalBaseLLM interface -------------------------------------------

    def load_model(self):
        from openai import OpenAI

        return OpenAI(base_url=OPENROUTER_BASE_URL, api_key=self._api_key)

    def get_model_name(self) -> str:
        return self._model_name

    def generate(self, prompt: str, schema: Any = None, **kwargs: Any) -> Any:
        messages, extra = self._request(prompt, schema)
        text = self._create(self.model, messages, extra)
        return self._coerce(text, schema)

    async def a_generate(self, prompt: str, schema: Any = None, **kwargs: Any) -> Any:
        messages, extra = self._request(prompt, schema)
        text = await self._a_create(messages, extra)
        return self._coerce(text, schema)

    # --- internals ------------------------------------------------------------

    def _aclient(self):
        if self._async_client is None:
            from openai import AsyncOpenAI

            self._async_client = AsyncOpenAI(
                base_url=OPENROUTER_BASE_URL, api_key=self._api_key
            )
        return self._async_client

    def _request(self, prompt: str, schema: Any) -> tuple[list[dict], dict]:
        system = _JUDGE_SYSTEM
        extra: dict[str, Any] = {}
        if schema is not None:
            system += (
                " Respond with ONE valid JSON object only, no markdown fences, "
                "matching this JSON schema: " + json.dumps(schema.model_json_schema())
            )
            extra["response_format"] = {"type": "json_object"}
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": str(prompt)},
        ]
        return messages, extra

    def _create(self, client, messages: list[dict], extra: dict) -> str:
        try:
            resp = client.chat.completions.create(
                model=self._model_name, messages=messages, temperature=0, **extra
            )
        except Exception:
            # Some models reject response_format; retry without it.
            resp = client.chat.completions.create(
                model=self._model_name, messages=messages, temperature=0
            )
        return resp.choices[0].message.content or ""

    async def _a_create(self, messages: list[dict], extra: dict) -> str:
        client = self._aclient()
        try:
            resp = await client.chat.completions.create(
                model=self._model_name, messages=messages, temperature=0, **extra
            )
        except Exception:
            resp = await client.chat.completions.create(
                model=self._model_name, messages=messages, temperature=0
            )
        return resp.choices[0].message.content or ""

    def _coerce(self, text: str, schema: Any) -> Any:
        if schema is None:
            return text
        try:
            return schema.model_validate_json(_extract_json_block(text))
        except Exception:
            return text  # let DeepEval's trimAndLoadJson handle the fallback


def judge_enabled() -> bool:
    return os.environ.get("TYRION_EVAL_JUDGE", "").lower() in {"1", "true", "yes"}


def build_judge() -> OpenRouterJudge:
    return OpenRouterJudge()