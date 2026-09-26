"""Convert a Tyrion AgentTrace into a Deepeval test case."""

from __future__ import annotations

from deepeval.test_case import LLMTestCase, ToolCall
from evals.trace import AgentTrace

def to_test_case(
    trace: AgentTrace,
    expected_tools: list[str],
    *,
    verification_passed: bool,
    verification_detail: str,
) -> LLMTestCase:
    return LLMTestCase(
        input=trace.task_input,
        actual_output = trace.final_output or "(agent produced no final message)",
        tools_called = [
            ToolCall(name = t.name, input_parameters=t.arguments) for t in trace.tool_calls
        ],
        expected_tools=[ToolCall(name=name) for name in expected_tools],
        additional_metadata = {
           "verification_passed": verification_passed,
            "verification_detail": verification_detail,
            "turn_count": trace.turn_count,
            "tool_count": len(trace.tool_calls), 
        },
    )
