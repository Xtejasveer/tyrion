"""Deterministic tool-correctness metric — no LLM.
"""

from __future__ import annotations

from deepeval.metrics import BaseMetric
from deepeval.test_case import LLMTestCase


class ToolCorrectnessMetric(BaseMetric):
    def __init__(self, threshold: float = 1.0) -> None:
        self.threshold = threshold

    def measure(self, test_case: LLMTestCase) -> float:
        expected = [t.name for t in (test_case.expected_tools or [])]
        called = [t.name for t in (test_case.tools_called or [])]
        called_set = set(called)

        if not expected:
            self.score = 1.0
            self.reason = "no expected tools specified"
        else:
            matched = sum(1 for name in expected if name in called_set)
            self.score = matched / len(expected)
            missing = [name for name in expected if name not in called_set]
            self.reason = (
                "all expected tools were called"
                if not missing
                else f"missing expected tools: {missing}; called: {called}"
            )

        self.success = self.score >= self.threshold
        return self.score

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        return self.measure(test_case)

    def is_successful(self) -> bool:
        return getattr(self, "success", False)

    @property
    def __name__(self) -> str:
        return "Tool Correctness"