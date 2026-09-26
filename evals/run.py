"""Run the Tyrion eval suite and print a deterministic scorecard.

    uv run --group evals python -m evals.run
"""

from __future__ import annotations

import asyncio

from evals.adapter import to_test_case
from evals.dataset import TASKS, EvalTask
from evals.metrics.code_correctness import CodeCorrectnessMetric
from evals.metrics.tool_correctness import ToolCorrectnessMetric
from evals.runner import run_task


async def evaluate_task(task: EvalTask) -> dict:
    trace, workspace = await run_task(task.id, task.fixture, task.prompt)
    passed, detail = task.verify(workspace)

    test_case = to_test_case(
        trace,
        task.expected_tools,
        verification_passed=passed,
        verification_detail=detail,
    )

    tool_metric = ToolCorrectnessMetric()
    tool_metric.measure(test_case)

    code_metric = CodeCorrectnessMetric()
    code_metric.measure(test_case)

    return {
        "task": task.id,
        "code": code_metric.score,
        "tools": tool_metric.score,
        "turns": trace.turn_count,
        "called": [t.name for t in trace.tool_calls],
        "detail": detail.splitlines()[-1] if detail else "",
    }


async def main() -> None:
    results: list[dict] = []
    for task in TASKS:
        print(f"Running {task.id}...")
        try:
            results.append(await evaluate_task(task))
        except Exception as exc:  # keep the report alive if one task blows up
            results.append(
                {
                    "task": task.id,
                    "code": 0.0,
                    "tools": 0.0,
                    "turns": 0,
                    "called": [],
                    "detail": f"ERROR: {exc}",
                }
            )

    print("\n" + "=" * 72)
    print(f"{'task':<16}{'code':>6}{'tools':>7}{'turns':>7}  called")
    print("-" * 72)
    for r in results:
        print(
            f"{r['task']:<16}{r['code']:>6.2f}{r['tools']:>7.2f}"
            f"{r['turns']:>7}  {r['called']}"
        )
    print("=" * 72)

    n = len(results)
    if n:
        code_avg = sum(r["code"] for r in results) / n
        tool_avg = sum(r["tools"] for r in results) / n
        print(f"averages: code={code_avg:.2f}  tools={tool_avg:.2f}")

    # Show any failure details underneath the table.
    for r in results:
        if r["detail"]:
            print(f"  - {r['task']}: {r['detail']}")


if __name__ == "__main__":
    asyncio.run(main())