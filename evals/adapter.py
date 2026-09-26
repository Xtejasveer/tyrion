"""Convert a Tyrion AgentTrace into a DeepEval test case.

Also synthesizes a DeepEval-compatible `_trace_dict` (a nested span tree) so
trace-requiring metrics like StepEfficiency and TaskCompletion can evaluate the
agent's actual step sequence, not just its final output.
"""

from __future__ import annotations

from deepeval.test_case import LLMTestCase, ToolCall

from evals.trace import AgentTrace


def _to_trace_dict(trace: AgentTrace) -> dict:
    """Build a DeepEval nested-span dict from our captured trace.

    Root is an 'agent' span carrying the task (input) and final answer (output);
    each tool call becomes a child 'tool' span in execution order, so the judge
    can see the full step sequence and spot redundancy.
    """
    children: list[dict] = []
    for t in trace.tool_calls:
        span: dict = {
            "name": t.name,
            "type": "tool",
            "input": t.arguments,
            "output": (t.result_text or "")[:500],
        }
        if t.is_error:
            span["error"] = (t.result_text or "")[:200]
        children.append(span)

    return {
        "name": "tyrion_coding_agent",
        "type": "agent",
        "input": trace.task_input,
        "output": trace.final_output or "(agent produced no final message)",
        "children": children,
    }


def to_test_case(
    trace: AgentTrace,
    expected_tools: list[str],
    *,
    verification_passed: bool,
    verification_detail: str,
) -> LLMTestCase:
    test_case = LLMTestCase(
        input=trace.task_input,
        actual_output=trace.final_output or "(agent produced no final message)",
        tools_called=[
            ToolCall(
                name=t.name,
                input_parameters=t.arguments,
                output=(t.result_text or "")[:500],
            )
            for t in trace.tool_calls
        ],
        expected_tools=[ToolCall(name=name) for name in expected_tools],
        additional_metadata={
            "verification_passed": verification_passed,
            "verification_detail": verification_detail,
            "turn_count": trace.turn_count,
            "tool_count": len(trace.tool_calls),
        },
    )
    # Attach the synthesized trace so trace-requiring metrics can run.
    test_case._trace_dict = _to_trace_dict(trace)
    return test_case