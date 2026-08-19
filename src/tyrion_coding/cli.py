"""CLI entry point for tyrion"""


from __future__ import annotations

import typer
import os 
import asyncio
import sys

from tyrion_ai.env import openai_compatible_config_from_env
from tyrion_ai.openai_compatible import OpenAICompatibleProvider
from tyrion_agent.harness import AgentHarness, AgentHarnessConfig
from tyrion_coding.rendering import PrintRenderer
from tyrion_coding.tools import create_coding_tools

app = typer.Typer(add_completion=False)
VERSION = "0.1.0"
SYSTEM_PROMPT = """You are tyrion, a terminal-based coding agent.
You help users by reading, writing, and editing files and running shell commands.

Guidelines:
- Read files before editing them to understand the current state.
- Use the edit tool for precise changes, write tool for the new files.
- Run tests after making changes to verify they work.
- Explain what you are doing and why.
- Be consice but thorough.
"""

@app.command()
def main(
    prompt: str = typer.Argument(None, help = "The prompt to send to the agent."),
    model: str = typer.Option("gpt-4.1-mini", "--model", "-m", help = "Model to use."),
    max_turns: int = typer.Option(None,"--max-turns", help = "Maximum agent turns."),
    version: bool = typer.Option(False, "--version","-v", help = "Show version and exit."),
) ->None:
    """Tyrion - A terminal coding agent"""
    if version:
        print(f"tyrion {VERSION}")
        raise typer.Exit()

    if prompt is None:
        if not sys.stdin.isatty():
            prompt = sys.stdin.read().strip()
        else:
            print("Usage: tyrion 'your prompt here'")
            print("     echo 'your prompt' | tyiron")
            raise typer.Exit(1)

    if not prompt:
        print("Error: empty prompt")
        raise typer.Exit(1)

    ## Run the agent
    asyncio.run(_run_agent(prompt, model, max_turns))

async def _run_agent(prompt: str, model:str, max_turns:int | None) -> None:
    """Set up and run the agent."""
    try:
        config = openai_compatible_config_from_env()
    except ValueError as exc:
        print(f"Error: {exc}")
        raise typer.Exit(1)
    
    provider = OpenAICompatibleProvider(config)

    # 2. Create the coding tools (read, write, edit, bash)
    cwd = os.getcwd()
    tools = create_coding_tools(cwd=cwd)
    # 3. Create the harness (the brain)
    harness = AgentHarness(
        AgentHarnessConfig(
            provider=provider,
            model=model,
            system=SYSTEM_PROMPT,
            tools=tools,
            max_turns=max_turns,
        )
    )
    # 4. Create the renderer (prints events to terminal)
    renderer = PrintRenderer()
    # 5. Run!
    renderer.console.print(f"[dim]Model: {model} | cwd: {os.getcwd()}[/dim]")
    renderer.console.print(f"[dim]{'─' * 50}[/dim]")
    async for event in harness.prompt(prompt):
        renderer.handle_event(event)

