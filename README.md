# ⚔️ Tyrion — Terminal-Native AI Coding Agent

<div align="center">

![Tyrion Terminal](https://raw.githubusercontent.com/Xtejasveer/tyrion/main/assets/welcome.png)

*A powerful, transparent, and responsive AI coding companion built directly for your terminal.*

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/)
[![Textual](https://img.shields.io/badge/built%20with-Textual-teal.svg)](https://textual.textualize.io/)
[![Tests: 200 passed](https://img.shields.io/badge/tests-200%20passed-success.svg)](#testing)
[![Architecture: Pi-derived](https://img.shields.io/badge/architecture-Pi--derived-gold.svg)](#architecture)

</div>

---

## 📦 Install

Works on **macOS and Linux**. On Windows, use [WSL](https://learn.microsoft.com/windows/wsl/install).

```bash
curl -LsSf https://raw.githubusercontent.com/Xtejasveer/tyrion/main/install.sh | sh
```

Then run `tyrion` to start. The script installs [`uv`](https://docs.astral.sh/uv/) if you don't have it, then installs Tyrion into its own isolated environment. You don't need Python installed (uv fetches Python 3.12 for you), and it never uses `sudo`. Want to read it first? [`install.sh`](install.sh) is short.

- **Update:** run the install command again.
- **Uninstall:** `uv tool uninstall tyrion-cli` (your chats and settings in `~/.tyrion` are left alone; delete that folder to remove them too).

---

## 📖 Overview

**Tyrion** is an autonomous terminal-native coding agent designed to pair-program with you directly inside your command line. Whether you are exploring an unfamiliar codebase, refactoring complex modules, fixing bugs, or writing unit tests, Tyrion provides a fluid, distraction-free environment that operates on your local workspace.

Equipped with filesystem tools, terminal execution capabilities, automatic token compaction, and in-UI provider switching, Tyrion pairs deep reasoning with responsive terminal aesthetics.

---

## 🏛️ Architecture

Tyrion's core engine architecture is derived from the **Pi coding agent architecture** developed by Mario Zechner (BadLogic Games). It adheres strictly to modular separation of concerns, separating pure stateless execution from stateful orchestration and persistence.

```
┌─────────────────────────────────────────────────────────────┐
│                    Presentation Layer                       │
│      Textual TUI (app.py)  │  Print CLI (cli.py / rendering)│
├─────────────────────────────────────────────────────────────┤
│                    Coding Domain Layer                      │
│   CodingSession  │  Coding Tools (read, write, edit, bash)  │
│   System Prompt Builder  │  Compaction & Token Accounting   │
├─────────────────────────────────────────────────────────────┤
│                    Agent Harness Layer                      │
│    AgentHarness (Stateful brain, cancellation, events)      │
│    Session Persistence (Append-only JSONL Tree)             │
├─────────────────────────────────────────────────────────────┤
│                    Pure Agent Loop Layer                    │
│      run_agent_loop (Stateless generator, turn manager)     │
├─────────────────────────────────────────────────────────────┤
│                    Model Provider Layer                     │
│    OpenAI-Compatible Streaming Provider (OpenRouter, etc.)  │
└─────────────────────────────────────────────────────────────┘
```

### Key Architectural Layers

1. **Pure Agent Loop (`src/tyrion_agent/loop.py`)**:
   - A completely **stateless generator** driving model-to-tool feedback cycles.
   - Emits fine-grained events (`AgentStartEvent`, `TurnStartEvent`, `MessageUpdateEvent`, `ToolExecutionStartEvent`, `ToolExecutionEndEvent`, `TurnEndEvent`, `AgentEndEvent`).
   - Knows nothing about disk persistence or frontends; simply consumes an immutable transcript and yields execution events.

2. **Agent Harness (`src/tyrion_agent/harness.py`)**:
   - The stateful supervisor that wraps the pure loop.
   - Manages message history, handles cooperative cancellation, dispatches events to listeners, and auto-repairs interrupted tool calls.

3. **Append-Only Tree Session Storage (`src/tyrion_agent/sessions/`)**:
   - Conversations are persisted to append-only JSONL logs on disk.
   - Sessions are structured as trees rather than linear lists, enabling branching, time-travel, and lossless restoration via `reconstruct_state()`.

4. **Model Provider Abstraction (`src/tyrion_ai/`)**:
   - High-performance, streaming SSE client supporting OpenAI, OpenRouter, DeepSeek, and local LLMs (Ollama, vLLM).
   - Captures real server-side token usage (`stream_options: {"include_usage": True}`) and features self-healing retries if a provider rejects usage flags.
   - Configurable context window limits and local override support via `~/.tyrion/model_limits.json`.

5. **Coding Domain & Tools (`src/tyrion_coding/`)**:
   - `CodingSession`: Coordinates the project workspace, loads project guidelines (`AGENTS.md` / instructions), and automatically assembles system prompts.
   - Real-time token compaction: Summarizes older conversation history using the model when nearing the 80% context window ceiling.

---

## 🎯 Use Cases

- **Codebase Exploration & Analysis**: Ask Tyrion to inspect directories, summarize module relationships, and trace function call graphs across unfamiliar repositories.
- **Hands-Off Multi-File Refactoring**: Prompt Tyrion to migrate legacy patterns or update dependencies; it reads targets, formulates plans, edits files, and verifies changes.
- **Bug Diagnosis & TDD**: Feed Tyrion a failing test suite or trace error; it will isolate the defect, apply precise edits, and re-run pytest until all tests are green.
- **Remote & SSH Pair Programming**: Full-featured interactive TUI that runs in headless servers, Docker containers, and SSH sessions without requiring a browser or Electron.

---

## ✨ Features

- 🎨 **Lannister Brand Theme**: Warm ink-black surfaces (`#0e0d10`, `#16151a`), rich Lannister gold (`#e0b04f`), crimson accents, and custom Pygments syntax highlighting designed for chat readability.
- ⌨️ **Interactive Slash Command Palette**: Type `/` anywhere in the prompt to open an instant auto-completing command menu with arrow-key navigation and keyboard shortcuts.
- ⚡ **Full Tool Arsenal**:
  - `read`: Reads files with line number indexing and byte caps.
  - `write`: Creates or replaces files safely.
  - `edit`: Precise substring replacements with uniqueness validation.
  - `bash`: Subprocess execution with process group termination (`os.killpg`) to eliminate orphan background processes.
- 🔌 **In-UI Connection (`/connect`)**: Connect your OpenRouter or OpenAI API keys directly within the app and have them saved in `~/.tyrion/credentials.json` (readable only by you).
- 📊 **Real-Time Token Usage Bar**: Dynamic status bar with visual block gauges (`▰▰▰▱▱▱`) displaying exact server-reported token usage against context limits.
- 🧹 **Automatic & Manual Compaction (`/compact`)**: Compresses long conversations into persistent summaries, preserving immediate context while keeping token usage lean.
- 🗂️ **Session Resuming (`/resume`)**: Visual session picker overlay allowing you to jump between past conversations and pick up right where you left off.

---

## 🛡️ Safety

Tyrion is early software (v0.1). Read this before pointing it at a project you care about:

- **It runs commands and edits files without asking.** The `bash`, `write` and `edit` tools act immediately and can reach any path your user can. Use it inside a git repository so you can review and undo changes (`git diff`, `git restore`).
- **Your code leaves your machine.** Your prompts and the files Tyrion reads are sent to the model provider you connect.
- **Your API key is stored in plain text** in `~/.tyrion/credentials.json`, readable only by you (permissions `600`). Prefer a key with a spending limit.
- **Files can carry instructions.** In an untrusted repository, a malicious file could try to steer the model into running commands.

---

## 🚀 Getting Started

> Just want to use Tyrion? See [Install](#-install) above. This section is for running it from source.

### Prerequisites

- Python 3.12+
- [`uv`](https://github.com/astral-sh/uv) (recommended) or `pip`

### Installation from source

Clone the repository and install dependencies:

```bash
git clone https://github.com/Xtejasveer/tyrion.git
cd tyrion
uv sync
```

### Running Tyrion

Launch the interactive Terminal User Interface:

```bash
uv run tyrion
```

*Tip: On first launch, run `/connect` to select your model provider (e.g. OpenRouter) and enter your API key.*

### Command-Line Usage

Tyrion also supports quick one-shot command-line runs:

```bash
# Ask a direct question
uv run tyrion "Explain how the routing works in src/api.py"

# Specify a model
uv run tyrion --model google/gemini-2.5-flash "Write unit tests for tools.py"

# Resume an existing session by ID
uv run tyrion --resume <session_id>

# Include a file's contents in the prompt
uv run tyrion "What is causing this traceback? $(cat error.log)"

# Or pipe the whole prompt in
cat prompt.txt | uv run tyrion
```

---

## 🕹️ Slash Commands Reference

| Command | Description |
| :--- | :--- |
| `/connect` | Open provider dialog to enter & persist your API key |
| `/model <name>` | Hot-swap active LLM model on the fly |
| `/resume` | Open visual session picker modal to switch conversations |
| `/compact` | Manually compress and summarize older conversation history |
| `/clear` | Wipe current transcript and return to centered landing screen |
| `/help` | List all available slash commands and descriptions |
| `/quit` / `/exit` | Gracefully exit the application |

---

## 🧪 Testing

Tyrion comes with a comprehensive test suite covering the agent loop, bash tool process isolation, SSE streaming, model limits, context compaction, TUI dialogs, command menu navigation, and theme rendering:

```bash
uv run pytest
```

```
============================= 200 passed in 17.28s =============================
```

---

## 🤝 Acknowledgements

Tyrion's core architecture and design principles are derived from the **Pi coding agent architecture** designed by [Mario Zechner](https://github.com/badlogic) ([BadLogic Games](https://badlogicgames.com/)). We extend our gratitude to Mario for the clean conceptual framework of separating the pure stateless agent loop from stateful harnesses and persistent session trees.

---

## 📜 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
