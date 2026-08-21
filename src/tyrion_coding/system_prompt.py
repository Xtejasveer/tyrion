"""Assemble the coding-agent system prompt from templates and project files."""

from __future__ import annotations

import platform 
from pathlib import Path

from tyrion_agent.tools import AgentTool
from tyrion_coding.prompt_templates import load_base_template, render_template
from tyrion_coding.resources import load_agents_markdown
from tyrion_coding.skills import discover_skills, format_skills

def format_tools(tools: list[AgentTool]) -> str:
    if not tools:
        return "(no tools available)"
    lines = [f"- '{tool.name}' : {tool.description}" for tool in tools]
    return "\n".join(lines)

def assemble_system_prompt(
        *,
        cwd: str | Path,
        tools: list[AgentTool],
        os_name: str | None = None,
) -> str:
    cwd_path = Path(cwd).resolve()
    base = render_template(
        load_base_template(),
        cwd = str(cwd_path),
        os = os_name or platform.system(),
        tools = format_tools(tools),
    )
    parts = [base.strip()]

    agents = load_agents_markdown(cwd_path)
    if agents:
        parts.append("# Project instructions (AGENTS.md)\n\n" + agents)

    skills_text = format_skills(discover_skills(cwd_path))
    if skills_text:
        parts.append(skills_text)

    return "\n\n".join(parts) + "\n"
