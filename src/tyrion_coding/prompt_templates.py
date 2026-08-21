"""Load and render bundled prompt templates."""

from __future__ import annotations

from importlib.resources import files

DEFAULT_TEMPLATE = """You are tyrion, a terminal-based coding agent.
You help users by reading, writing, and editing files and running shell commands.

## Runtime
- Working directory: {{cwd}}
- Operating system: {{os}}

## Tools
{{tools}}

## Guidelines
- Read files before editing them to understand the current state.
- Use the edit tool for precise changes, write tool for new files.
- Run tests after making changes to verify they work.
- Explain what you are doing and why.
- Be concise but thorough.

If a Skills section is present, follow those instructions when they apply.
If project instructions are present, they override these defaults for that repo.
"""


def load_base_template() -> str:
    try:
        path = files("tyrion_coding.data").joinpath("system_prompt.md")
        return path.read_text(encoding="utf-8")
    except (FileNotFoundError, ModuleNotFoundError, OSError):
        return DEFAULT_TEMPLATE


def render_template(template: str, **variables: str) -> str:
    rendered = template
    for key, value in variables.items():
        rendered = rendered.replace("{{" + key + "}}", value)
    return rendered