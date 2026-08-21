"""CLI entry point for tyrion"""

from __future__ import annotations

import asyncio
import os
import sys
import typer

from tyrion_ai.env import openai_compatible_config_from_env
from tyrion_ai.openai_compatible import OpenAICompatibleProvider
from tyrion_coding.rendering import PrintRenderer
from tyrion_coding.session import CodingSession
from tyrion_coding.session_coding import SessionManager

app = typer.Typer(add_completion=False)
VERSION = "0.1.0"
SYSTEM_PROMPT = """You are tyrion, a terminal-based coding agent.
You help users by reading, writing, and editing files and running shell commands.

Guidelines:
- Read files before editing them to understand the current state.
- Use the edit tool for precise changes, write tool for the new files.
- Run tests after making changes to verify they work.
- Explain what you are doing and why.
- Be concise but thorough.
"""

@app.command()
def main(
    prompt: str = typer.Argument(None, help="The prompt to send to the agent."),
    model: str = typer.Option("gpt-4.1-mini", "--model", "-m", help="Model to use."),
    max_turns: int = typer.Option(None, "--max-turns", help="Maximum agent turns."),
    version: bool = typer.Option(False, "--version", "-v", help="Show version and exit."),
    resume: str | None = typer.Option(
        None, "--resume", "-r", help="Resume a previous session id."
    ),
) -> None:
    """Tyrion - A terminal coding agent"""
    if version:
        print(f"tyrion {VERSION}")
        raise typer.Exit()

    if prompt is None:
        if not sys.stdin.isatty():
            prompt = sys.stdin.read().strip()
            if not prompt:
                print("Error: empty prompt")
                raise typer.Exit(1)
            asyncio.run(_run_agent(prompt, model, max_turns, resume))
        else:
            # Interactive mode: launch TUI
            _run_tui(model, max_turns, resume)
    else:
        if not prompt.strip():
            print("Error: empty prompt")
            raise typer.Exit(1)
        asyncio.run(_run_agent(prompt, model, max_turns, resume))


async def _run_agent(
    prompt: str,
    model: str,
    max_turns: int | None,
    resume: str | None,
) -> None:
    try:
        config = openai_compatible_config_from_env()
    except ValueError as exc:
        print(f"Error: {exc}")
        raise typer.Exit(1)

    provider = OpenAICompatibleProvider(config)
    cwd = os.getcwd()
    manager = SessionManager()

    if resume:
        storage = manager.storage_for(resume)
        if not storage.path.exists():
            print(f"Error: session not found: {resume}")
            raise typer.Exit(1)
        session = CodingSession(
            cwd=cwd,
            provider=provider,
            model=model,
            system=SYSTEM_PROMPT,
            storage=storage,
            session_id=resume,
            max_turns=max_turns,
        )
        await session.resume()
    else:
        session_id, storage = manager.new_storage()
        session = CodingSession(
            cwd=cwd,
            provider=provider,
            model=model,
            system=SYSTEM_PROMPT,
            storage=storage,
            session_id=session_id,
            max_turns=max_turns,
        )

    renderer = PrintRenderer()
    renderer.console.print(
        f"[dim]Model: {model} | cwd: {cwd} | session: {session.session_id}[/dim]"
    )
    renderer.console.print(f"[dim]{'─' * 50}[/dim]")
    async for event in session.prompt(prompt):
        renderer.handle_event(event)


def _run_tui(
    model: str,
    max_turns: int | None,
    resume: str | None,
) -> None:
    try:
        config = openai_compatible_config_from_env()
    except ValueError as exc:
        print(f"Error: {exc}")
        raise typer.Exit(1)

    provider = OpenAICompatibleProvider(config)
    cwd = os.getcwd()
    manager = SessionManager()

    if resume:
        storage = manager.storage_for(resume)
        if not storage.path.exists():
            print(f"Error: session not found: {resume}")
            raise typer.Exit(1)
        session = CodingSession(
            cwd=cwd,
            provider=provider,
            model=model,
            system=None,  # Resolves dynamically
            storage=storage,
            session_id=resume,
            max_turns=max_turns,
        )
    else:
        session_id, storage = manager.new_storage()
        session = CodingSession(
            cwd=cwd,
            provider=provider,
            model=model,
            system=None,  # Resolves dynamically
            storage=storage,
            session_id=session_id,
            max_turns=max_turns,
        )

    from tyrion_coding.tui.app import TyrionApp
    tui_app = TyrionApp(session=session)
    tui_app.run()