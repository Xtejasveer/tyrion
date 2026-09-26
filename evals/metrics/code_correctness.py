"""Deterministic code-correctness metric.
Reads the verification result the runner already computed (e.g. did pytest pass)
off the testcase. No LLM- fully reproducible, 1 or 0.
"""

from __future__ import annotations
from deepeval.metrics import BaseMetric
from deepeval.test_case import LLMTestCase

class CodeCorrectnessMetric(BaseMetric):
    def __init__(self, threshold: float = 1.0) -> None:
        self.threshold = threshold

    def measure(self, test_case: LLMTestCase) -> float:
        meta = test_case.additional_metadata or {}
        passed = bool(meta.get("verification_passed", False))
        self.score = 1.0 if passed else 0.0
        self.success = self.score >= self.threshold
        self.reason = meta.get("verification_detail", "no verification detail")
        return self.score

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        return self.measure(test_case)

    def is_successful(self) -> bool:
        return getattr(self, "success", False)

    @property
    def __name__(self) -> str:
        return "Code Correctness"