"""Golden tasks. Each task = a prompt, a fixture, expected tools, a verifier."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from evals import verify


@dataclass
class EvalTask:
    id: str
    fixture: str
    prompt: str
    expected_tools: list[str] = field(default_factory=list)
    verify: Callable[[Path], tuple[bool, str]] = verify.run_pytest


TASKS: list[EvalTask] = [
    EvalTask(
        id="bugfix_add",
        fixture="bugfix_add",
        prompt=(
            "The tests in test_calculator.py are failing. Find and fix the bug "
            "in calculator.py so that all tests pass. Do not edit the tests."
        ),
        expected_tools=["read", "edit"],
        verify=verify.run_pytest,
    ),
    EvalTask(
        id="add_test",
        fixture="add_test",
        prompt=(
            "test_mathops.py only tests `add`. Add a new test function that "
            "tests the `subtract` function from mathops.py. Do not modify mathops.py."
        ),
        expected_tools=["read", "edit"],
        verify=verify.all_of(
            verify.run_pytest,
            lambda ws: verify.file_contains(ws, "test_mathops.py", "subtract"),
        ),
    ),
    EvalTask(
        id="refactor_rename",
        fixture="refactor_rename",
        prompt=(
            "Rename the function `calc_total` to `compute_total` in billing.py, "
            "including its usages within that file, so the tests still pass. "
            "Do not edit the tests."
        ),
        expected_tools=["read", "edit"],
        verify=verify.all_of(
            verify.run_pytest,
            lambda ws: verify.file_contains(ws, "billing.py", "compute_total"),
            lambda ws: verify.file_excludes(ws, "billing.py", "calc_total"),
        ),
    ),
    EvalTask(
        id="multifile_edit",
        fixture="multifile_edit",
        prompt=(
            "The test expects total_with_tax(100) == 110.0 (a 10% tax). Fix the "
            "code so the test passes — you will need to change both config.py and "
            "pricing.py. Do not edit the test."
        ),
        expected_tools=["read", "edit"],
        verify=verify.run_pytest,
    ),
    EvalTask(
        id="implement_function",
        fixture="implement_function",
        prompt=(
            "Implement the `is_palindrome` function in strings_util.py so all "
            "tests pass. Do not edit the tests."
        ),
        expected_tools=["read", "edit"],
        verify=verify.run_pytest,
    ),
    EvalTask(
        id="read_only_explain",
        fixture="read_only_explain",
        prompt=(
            "Explain in one or two sentences what the function `mystery` in "
            "mystery.py does. Do not modify any files."
        ),
        expected_tools=["read"],
        verify=lambda ws: verify.files_unchanged(ws, "read_only_explain"),
    ),
    EvalTask(
        id="failing_import",
        fixture="failing_import",
        prompt=(
            "Running the tests raises an ImportError from shapes.py. Fix the "
            "broken import so the tests pass. Do not edit geometry.py or the tests."
        ),
        expected_tools=["read", "edit"],
        verify=verify.run_pytest,
    ),
]