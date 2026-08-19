"""Built-in coding tools: read, write, edit, bash."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import tempfile
from collections.abc import Mapping
from pathlib import Path

from tyrion_agent.messages import TextContent
from tyrion_agent.tools import (
    AgentTool,
    AgentToolResult,
    ToolCancellationToken,
    ToolUpdateCallback,
)
from tyrion_agent.types import JSONValue


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_READ_LINES = 2000
MAX_READ_BYTES = 50_000
MAX_OUTPUT_LINES = 2000
MAX_OUTPUT_BYTES = 50_000


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _resolve_path(cwd: Path, path_arg: str) -> Path:
    """Resolve a path argument against the working directory."""
    p = Path(path_arg)
    if p.is_absolute():
        return p
    return (cwd / p).resolve()


def _error(message: str) -> AgentToolResult:
    """Create an error tool result."""
    return AgentToolResult(content=[TextContent(text=message)])


# ---------------------------------------------------------------------------
# READ tool
# ---------------------------------------------------------------------------


def create_read_tool(cwd: str | Path = ".") -> AgentTool:
    """Create a tool that reads files from disk."""

    cwd_path = Path(cwd).resolve()

    async def execute(
        tool_call_id: str,
        arguments: Mapping[str, JSONValue],
        signal: ToolCancellationToken | None = None,
        on_update: ToolUpdateCallback | None = None,
    ) -> AgentToolResult:
        # Validate arguments
        path_arg = arguments.get("path")
        if not isinstance(path_arg, str) or not path_arg:
            return _error("'path' argument is required and must be a string.")

        resolved = _resolve_path(cwd_path, path_arg)

        if not resolved.exists():
            return _error(f"File not found: {resolved}")

        if resolved.is_dir():
            return _error(f"Path is a directory, not a file: {resolved}")

        # Parse optional offset and limit
        offset = arguments.get("offset", 0)
        limit = arguments.get("limit")

        if not isinstance(offset, int) or offset < 0:
            return _error("'offset' must be a non-negative integer.")

        if limit is not None and (not isinstance(limit, int) or limit < 1):
            return _error("'limit' must be a positive integer.")

        # Read the file
        try:
            text = resolved.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return _error(f"Cannot read file as UTF-8 text: {resolved}")
        except OSError as exc:
            return _error(f"Cannot read file: {exc}")

        # Apply offset and limit
        lines = text.splitlines(keepends=True)
        total_lines = len(lines)

        if offset > 0:
            # offset is 1-indexed
            start = offset - 1
        else:
            start = 0

        if start >= total_lines:
            return _error(
                f"Offset {offset} is beyond the end of the file ({total_lines} lines)."
            )

        if limit is not None:
            end = start + limit
        else:
            end = total_lines

        selected = lines[start:end]

        # Truncate if too large
        output = ""
        line_count = 0
        for line in selected:
            if line_count >= MAX_READ_LINES or len(output.encode()) >= MAX_READ_BYTES:
                remaining = total_lines - (start + line_count)
                output += f"\n[{remaining} more lines. Use offset={start + line_count + 1} to continue.]"
                break
            output += line
            line_count += 1

        return AgentToolResult(
            content=[TextContent(text=output)],
            details={
                "path": str(resolved),
                "lines": line_count,
                "totalLines": total_lines,
            },
        )

    return AgentTool(
        name="read",
        description=(
            "Read the contents of a file. "
            "Use 'offset' (1-indexed line number) and 'limit' to read specific sections."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path to read (relative to working directory).",
                },
                "offset": {
                    "type": "integer",
                    "description": "1-indexed line number to start reading from.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of lines to return.",
                },
            },
            "required": ["path"],
        },
        execute_fn=execute,
    )


# ---------------------------------------------------------------------------
# WRITE tool
# ---------------------------------------------------------------------------


def create_write_tool(cwd: str | Path = ".") -> AgentTool:
    """Create a tool that writes files to disk."""

    cwd_path = Path(cwd).resolve()

    async def execute(
        tool_call_id: str,
        arguments: Mapping[str, JSONValue],
        signal: ToolCancellationToken | None = None,
        on_update: ToolUpdateCallback | None = None,
    ) -> AgentToolResult:
        path_arg = arguments.get("path")
        if not isinstance(path_arg, str) or not path_arg:
            return _error("'path' argument is required and must be a string.")

        content = arguments.get("content")
        if not isinstance(content, str):
            return _error("'content' argument is required and must be a string.")

        resolved = _resolve_path(cwd_path, path_arg)

        try:
            # Create parent directories if they don't exist
            resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_text(content, encoding="utf-8")
        except OSError as exc:
            return _error(f"Cannot write file: {exc}")

        return AgentToolResult(
            content=[TextContent(text=f"Wrote {len(content)} characters to {resolved}")],
            details={
                "path": str(resolved),
                "characters": len(content),
            },
        )

    return AgentTool(
        name="write",
        description="Create or overwrite a file with the given content.",
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path to write (relative to working directory).",
                },
                "content": {
                    "type": "string",
                    "description": "Complete file contents to write.",
                },
            },
            "required": ["path", "content"],
        },
        execute_fn=execute,
    )


# ---------------------------------------------------------------------------
# EDIT tool
# ---------------------------------------------------------------------------


def create_edit_tool(cwd: str | Path = ".") -> AgentTool:
    """Create a tool that applies exact text replacements to a file."""

    cwd_path = Path(cwd).resolve()

    async def execute(
        tool_call_id: str,
        arguments: Mapping[str, JSONValue],
        signal: ToolCancellationToken | None = None,
        on_update: ToolUpdateCallback | None = None,
    ) -> AgentToolResult:
        path_arg = arguments.get("path")
        if not isinstance(path_arg, str) or not path_arg:
            return _error("'path' argument is required and must be a string.")

        edits = arguments.get("edits")
        if not isinstance(edits, list) or not edits:
            return _error("'edits' argument is required and must be a non-empty list.")

        resolved = _resolve_path(cwd_path, path_arg)

        if not resolved.exists():
            return _error(f"File not found: {resolved}")

        if resolved.is_dir():
            return _error(f"Path is a directory: {resolved}")

        # Read original content
        try:
            original = resolved.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as exc:
            return _error(f"Cannot read file: {exc}")

        # Validate all edits BEFORE applying any
        for i, edit in enumerate(edits):
            if not isinstance(edit, dict):
                return _error(f"Edit {i} must be an object with 'oldText' and 'newText'.")

            old_text = edit.get("oldText", "")
            new_text = edit.get("newText", "")

            if not isinstance(old_text, str) or not old_text:
                return _error(f"Edit {i}: 'oldText' must be a non-empty string.")
            if not isinstance(new_text, str):
                return _error(f"Edit {i}: 'newText' must be a string.")

            count = original.count(old_text)
            if count == 0:
                # Show a snippet to help debug
                preview = old_text[:80].replace("\n", "\\n")
                return _error(f"Edit {i}: 'oldText' not found in file: \"{preview}\"")
            if count > 1:
                return _error(
                    f"Edit {i}: 'oldText' appears {count} times. It must be unique."
                )

        # Apply all edits
        result = original
        for edit in edits:
            old_text = edit["oldText"]
            new_text = edit["newText"]
            result = result.replace(old_text, new_text, 1)

        if result == original:
            return _error("All edits would leave the file unchanged.")

        # Write the result
        try:
            resolved.write_text(result, encoding="utf-8")
        except OSError as exc:
            return _error(f"Cannot write file: {exc}")

        return AgentToolResult(
            content=[TextContent(text=f"Applied {len(edits)} edit(s) to {resolved}")],
            details={
                "path": str(resolved),
                "edits": len(edits),
            },
        )

    return AgentTool(
        name="edit",
        description=(
            "Apply exact text replacements to a file. Each edit must have "
            "'oldText' (unique in the file) and 'newText'."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path to edit.",
                },
                "edits": {
                    "type": "array",
                    "description": "List of replacements to apply.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "oldText": {
                                "type": "string",
                                "description": "Exact text to find (must appear exactly once).",
                            },
                            "newText": {
                                "type": "string",
                                "description": "Replacement text.",
                            },
                        },
                        "required": ["oldText", "newText"],
                    },
                },
            },
            "required": ["path", "edits"],
        },
        execute_fn=execute,
    )


# ---------------------------------------------------------------------------
# BASH tool
# ---------------------------------------------------------------------------


def create_bash_tool(cwd: str | Path = ".") -> AgentTool:
    """Create a tool that executes shell commands."""

    cwd_path = Path(cwd).resolve()

    async def execute(
        tool_call_id: str,
        arguments: Mapping[str, JSONValue],
        signal: ToolCancellationToken | None = None,
        on_update: ToolUpdateCallback | None = None,
    ) -> AgentToolResult:
        command = arguments.get("command")
        if not isinstance(command, str) or not command:
            return _error("'command' argument is required and must be a string.")

        timeout = arguments.get("timeout")
        if timeout is not None:
            if not isinstance(timeout, (int, float)) or timeout <= 0:
                return _error("'timeout' must be a positive number.")

        timed_out = False
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=str(cwd_path),
                start_new_session=True,  # so we can kill the whole group
            )

            try:
                stdout_bytes, _ = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                timed_out = True
                # Kill the entire process group
                try:
                    os.killpg(proc.pid, 9)
                except (ProcessLookupError, PermissionError):
                    proc.kill()
                stdout_bytes, _ = await proc.communicate()

        except OSError as exc:
            return _error(f"Cannot execute command: {exc}")

        # Decode output
        output = stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""
        exit_code = proc.returncode

        # Truncate if too large (keep the TAIL, not the head)
        truncated = False
        lines = output.splitlines(keepends=True)
        if len(lines) > MAX_OUTPUT_LINES:
            lines = lines[-MAX_OUTPUT_LINES:]
            truncated = True
            output = "".join(lines)
        if len(output.encode()) > MAX_OUTPUT_BYTES:
            output = output[-MAX_OUTPUT_BYTES:]
            truncated = True

        # If truncated, save full output to a temp file
        full_output_path = None
        if truncated:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".log", delete=False, encoding="utf-8"
            ) as f:
                f.write(stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else "")
                full_output_path = f.name
            output = f"[Output truncated. Full output saved to {full_output_path}]\n\n" + output

        # Build result message
        if timed_out:
            text = f"Command timed out after {timeout}s.\n\n{output}"
            is_error_result = True
        elif exit_code != 0:
            text = f"Command failed with exit code {exit_code}.\n\n{output}"
            is_error_result = True
        else:
            text = output
            is_error_result = False

        result = AgentToolResult(
            content=[TextContent(text=text)],
            details={
                "command": command,
                "exitCode": exit_code,
                "timedOut": timed_out,
                "truncated": truncated,
            },
        )

        # Note: we return the result, and the loop handles is_error
        # For bash, non-zero exit = error result, but we still return
        # the output so the model can see what went wrong.
        # However, AgentToolResult doesn't have an is_error field —
        # the loop determines that from _run_tool. For bash specifically,
        # we raise an exception for the loop to catch if it's an error.
        if is_error_result:
            raise RuntimeError(text)

        return result

    return AgentTool(
        name="bash",
        description=(
            "Execute a shell command in the working directory. "
            "Use 'timeout' to set a maximum runtime in seconds."
        ),
        parameters={
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute.",
                },
                "timeout": {
                    "type": "number",
                    "description": "Maximum runtime in seconds.",
                },
            },
            "required": ["command"],
        },
        execute_fn=execute,
    )


# ---------------------------------------------------------------------------
# Convenience: create all coding tools at once
# ---------------------------------------------------------------------------


def create_coding_tools(cwd: str | Path = ".") -> list[AgentTool]:
    """Create all four built-in coding tools."""
    return [
        create_read_tool(cwd),
        create_write_tool(cwd),
        create_edit_tool(cwd),
        create_bash_tool(cwd),
    ]