"""bash tool: output, timeout and cancellation."""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

import pytest

from tyrion_agent.harness import SimpleCancellationToken
from tyrion_coding.tools import create_bash_tool


@pytest.mark.asyncio
async def test_bash_returns_output(tmp_path: Path) -> None:
    result = await create_bash_tool(tmp_path).execute("id", {"command": "echo hi"})

    assert result.text == "hi\n"


@pytest.mark.asyncio
async def test_bash_timeout_kills_the_command(tmp_path: Path) -> None:
    started = time.monotonic()

    with pytest.raises(RuntimeError, match="timed out"):
        await create_bash_tool(tmp_path).execute(
            "id", {"command": "sleep 30", "timeout": 0.5}
        )

    assert time.monotonic() - started < 5


@pytest.mark.asyncio
async def test_bash_stops_a_running_command_when_cancelled(tmp_path: Path) -> None:
    token = SimpleCancellationToken()
    pid_file = tmp_path / "pid"

    async def cancel_soon() -> None:
        await asyncio.sleep(0.5)
        token.cancel()

    canceller = asyncio.create_task(cancel_soon())
    started = time.monotonic()

    with pytest.raises(RuntimeError, match="cancelled"):
        await create_bash_tool(tmp_path).execute(
            "id", {"command": f"echo $$ > {pid_file}; sleep 30"}, token
        )
    await canceller

    assert time.monotonic() - started < 5  # did not wait for `sleep 30`
    with pytest.raises(ProcessLookupError):  # and the process really is gone
        os.kill(int(pid_file.read_text()), 0)
