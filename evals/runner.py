"""Run a single eval task headlessly and capture its trace"""

from __future__ import annotations

from pathlib import Path

from tyrion_agent.sessions.jsonl import JsonlSessionStorage
from tyrion_coding.session import CodingSession

from evals.config import build_generator, max_turns
from evals.sandbox import prepare_workspace
from evals.trace import AgentTrace, TraceCollector

async def run_task(task_id: str, fixture: str, prompt: str) -> tuple[AgentTrace, Path]:
    """Execute one task in a sandbox and return (trace, workspace)"""
    workspace = prepare_workspace(fixture, task_id)
    provider, model = build_generator()

    storage = JsonlSessionStorage(workspace /".eval_session.jsonl")
    session = CodingSession(
        cwd = workspace,
        provider=provider,
        model = model,
        storage = storage,
        max_turns = max_turns()
    )

    collector = TraceCollector(prompt)
    async for event in session.prompt(prompt):
        collector.observe(event)
    return collector.build(), workspace