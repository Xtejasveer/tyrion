"""Run the Tyrion eval suite and print a scorecard.

Deterministic metrics always run (free). LLM-judged DeepEval metrics run only
when TYRION_EVAL_JUDGE=1 (they call the judge model and cost a little).

    uv run --group evals python -m evals.run                      # deterministic only
    TYRION_EVAL_JUDGE=1 uv run --group evals python -m evals.run  # + LLM judge
"""

from __future__ import annotations

import asyncio
import os

from deepeval.metrics import (
    ArgumentCorrectnessMetric,
    StepEfficiencyMetric,
    TaskCompletionMetric,
)

from evals.adapter import to_test_case
from evals.dataset import TASKS, EvalTask
from evals.judge import build_judge, judge_enabled
from evals.metrics.code_correctness import CodeCorrectnessMetric
from evals.metrics.tool_correctness import ToolCorrectnessMetric
from evals.runner import run_task


async def _judge(metric, test_case) -> tuple[float | None, str]:
    """Run one judged metric, tolerating failures so one bad call won't abort."""
    try:
        await metric.a_measure(test_case)
        return float(metric.score), (metric.reason or "").replace("\n", " ")[:90]
    except Exception as exc:
        return None, f"ERR: {exc}"[:90]


async def evaluate_task(task: EvalTask, judge) -> dict:
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

    detail_text = detail.splitlines()[-1] if detail else ""
    if trace.errors:
        detail_text = f"PROVIDER ERROR: {trace.errors[-1][:160]}"

    row: dict = {
        "task": task.id,
        "code": code_metric.score,
        "tools": tool_metric.score,
        "turns": trace.turn_count,
        "called": [t.name for t in trace.tool_calls],
        "detail": detail_text,
    }

    if judge is not None:
        tcomp = TaskCompletionMetric(model=judge, task=task.prompt)
        argc = ArgumentCorrectnessMetric(model=judge)
        steff = StepEfficiencyMetric(model=judge)
        row["tcomp"], row["tcomp_reason"] = await _judge(tcomp, test_case)
        row["argc"], row["argc_reason"] = await _judge(argc, test_case)
        row["steff"], row["steff_reason"] = await _judge(steff, test_case)

    return row


async def main() -> None:
    judge = build_judge() if judge_enabled() else None
    if judge is not None:
        print(f"LLM judge: {judge.get_model_name()} (via OpenRouter)\n")

    results: list[dict] = []
    for task in TASKS:
        print(f"Running {task.id}...")
        try:
            results.append(await evaluate_task(task, judge))
        except Exception as exc:
            results.append(
                {
                    "task": task.id, "code": 0.0, "tools": 0.0, "turns": 0,
                    "called": [], "detail": f"ERROR: {exc}",
                }
            )

    judged = judge is not None
    print("\n" + "=" * 92)
    header = f"{'task':<18}{'code':>6}{'tools':>7}"
    if judged:
        header += f"{'tcomp':>7}{'argc':>7}{'steff':>7}"
    header += f"{'turns':>7}  called"
    print(header)
    print("-" * 92)

    def fmt(v) -> str:
        return f"{v:>7.2f}" if isinstance(v, (int, float)) else f"{'n/a':>7}"

    for r in results:
        line = f"{r['task']:<18}{r['code']:>6.2f}{r['tools']:>7.2f}"
        if judged:
            line += fmt(r.get("tcomp")) + fmt(r.get("argc")) + fmt(r.get("steff"))
        line += f"{r['turns']:>7}  {r['called']}"
        print(line)
    print("=" * 92)

    n = len(results)
    if n:
        def avg(key):
            vals = [r[key] for r in results if isinstance(r.get(key), (int, float))]
            return sum(vals) / len(vals) if vals else float("nan")

        summary = f"averages: code={avg('code'):.2f}  tools={avg('tools'):.2f}"
        if judged:
            summary += (
                f"  tcomp={avg('tcomp'):.2f}  argc={avg('argc'):.2f}"
                f"  steff={avg('steff'):.2f}"
            )
        print(summary)

    if judged and os.environ.get("TYRION_EVAL_REASONS", "").lower() in {"1", "true", "yes"}:
        print("\n--- judge reasons ---")
        for r in results:
            print(f"\n{r['task']}  (tcomp={r.get('tcomp')}, argc={r.get('argc')}, steff={r.get('steff')})")
            print(f"  task completion : {r.get('tcomp_reason', '')}")
            print(f"  argument corr.  : {r.get('argc_reason', '')}")
            print(f"  step efficiency : {r.get('steff_reason', '')}")

    for r in results:
        if r.get("detail"):
            print(f"  - {r['task']}: {r['detail']}")


if __name__ == "__main__":
    asyncio.run(main())