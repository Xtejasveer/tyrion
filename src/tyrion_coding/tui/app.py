from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.css.query import NoMatches
from textual.widgets import TextArea

from tyrion_agent.events import (
    MessageEndEvent,
    MessageUpdateEvent,
    ToolExecutionEndEvent,
    ToolExecutionStartEvent,
)
from tyrion_agent.messages import (
    AgentMessage,
    AssistantMessage,
    ToolResultMessage,
    UserMessage,
)
from tyrion_coding.session_coding import SessionManager
from tyrion_coding.theme import RICH_THEME
from tyrion_coding.tui.styles import APP_CSS, TYRION_THEME
from tyrion_coding.tui.welcome import WelcomeHeader, WelcomeHints, WelcomeTip
from tyrion_coding.tui.widgets import (
    MessageWidget,
    PromptBox,
    PromptInput,
    ThinkingIndicator,
    ToolCallWidget,
    TUIStatusBar,
)

if TYPE_CHECKING:
    from tyrion_coding.session import CodingSession


class TyrionApp(App[None]):
    """Tyrion Interactive Terminal User Interface."""

    CSS = APP_CSS
    TITLE = "Tyrion"

    BINDINGS = [
        ("escape", "cancel_run", "Cancel execution"),
        ("ctrl+c", "quit", "Quit"),
    ]

    def __init__(self, session: CodingSession) -> None:
        super().__init__()
        self.session = session
        # Colors for markdown rendered inside widgets, and for Textual's own widgets.
        self.console.push_theme(RICH_THEME)
        self.register_theme(TYRION_THEME)
        self.theme = TYRION_THEME.name

    def compose(self) -> ComposeResult:
        yield VerticalScroll(id="transcript-container")
        yield ThinkingIndicator(id="thinking")
        with Vertical(id="welcome-wrapper"):
            yield WelcomeHeader(id="welcome-header")
            yield PromptBox(model_name=self.session.harness.config.model, id="prompt-box")
            yield WelcomeHints(id="welcome-hints")
            yield WelcomeTip(id="welcome-tip")
        yield TUIStatusBar(
            session_id=self.session.session_id,
            model=self.session.harness.config.model,
            cwd=str(self.session.cwd),
        )

    def set_chat_active(self, active: bool) -> None:
        """Switch between centered welcome mode and scrollable chat mode."""
        if active:
            self.screen.add_class("chat-active")
            self.add_class("chat-active")
        else:
            self.screen.remove_class("chat-active")
            self.remove_class("chat-active")

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        """Keep the newest messages in view while the command list opens and closes.

        The list takes room from the transcript, which would otherwise hide the
        bottom of it. Only a transcript already at the bottom is moved.
        """
        try:
            transcript = self.query_one("#transcript-container", VerticalScroll)
        except NoMatches:
            return
        if transcript.scroll_y >= transcript.max_scroll_y - 1:
            self.call_after_refresh(transcript.scroll_end, animate=False)

    def on_mount(self) -> None:
        """Actions to run when screen mounts."""
        self.transcript_view = self.query_one("#transcript-container", VerticalScroll)
        self.thinking_indicator = self.query_one("#thinking", ThinkingIndicator)
        self.prompt_box = self.query_one("#prompt-box", PromptBox)
        self.prompt_input = self.query_one("#prompt-input", PromptInput)
        self.status_bar = self.query_one(TUIStatusBar)
        self.prompt_input.focus()
        self.init_session()
        self.check_initial_auth()
        self.warn_if_unknown_model(self.session.harness.config.model)

    def check_initial_auth(self) -> None:
        """If unauthenticated on startup, automatically open ConnectModal."""
        provider = self.session.harness.config.provider
        api_key = getattr(getattr(provider, "_config", None), "api_key", "")
        if api_key in ("", "unauthenticated"):
            self.prompt_connect()

    def prompt_connect(self) -> None:
        """Open ConnectModal and apply result via callback."""
        from tyrion_coding.tui.connect_modal import ConnectModal

        def on_connected(result: tuple[str, str] | None) -> None:
            if result:
                provider_name, key = result
                self.run_worker(self.apply_connection(provider_name, key))

        self.push_screen(ConnectModal(), callback=on_connected)

    async def apply_connection(self, provider_name: str, api_key: str) -> None:
        """Apply new credentials, hot-swap provider, and update UI."""
        from tyrion_coding.provider_config import connect_provider

        provider, default_model = connect_provider(provider_name, api_key)
        self.session.harness.config.provider = provider
        self.session.harness.config.model = default_model

        self.status_bar.model = default_model
        self.prompt_box.set_model(default_model)
        self.update_token_display()

        self.set_chat_active(True)
        await self.transcript_view.mount(
            MessageWidget(
                role="system",
                text=(
                    f"**Connected to {provider_name.capitalize()}**\n\n"
                    f"- Model: `{default_model}`\n"
                    "- Your API key was saved on this machine for future sessions.\n\n"
                    "Start typing below."
                ),
            )
        )
        self.transcript_view.scroll_end()
        self.prompt_input.focus()

    async def show_history(self, messages: Sequence[AgentMessage]) -> None:
        """Show a stored conversation in the transcript."""
        self.set_chat_active(bool(messages))

        # Tyrion's name goes on the first thing it says after each user message.
        label_next = True
        for index, msg in enumerate(messages):
            if isinstance(msg, UserMessage):
                await self.transcript_view.mount(MessageWidget("user", msg.content))
                label_next = True
            elif isinstance(msg, AssistantMessage):
                if msg.text:
                    await self.transcript_view.mount(
                        MessageWidget("assistant", msg.text, show_label=label_next)
                    )
                    label_next = False
                for tool_call in msg.tool_calls:
                    result = next(
                        (
                            later
                            for later in messages[index + 1 :]
                            if isinstance(later, ToolResultMessage)
                            and later.tool_call_id == tool_call.id
                        ),
                        None,
                    )
                    tool_widget = ToolCallWidget(tool_call.name, tool_call.arguments)
                    if result is not None:
                        tool_widget.set_result(result.text, result.is_error)
                    await self.transcript_view.mount(tool_widget)

        self.transcript_view.scroll_end()

    @work
    async def init_session(self) -> None:
        """Initialize the session and load conversation history."""
        self.status_bar.set_status("Initializing...")
        try:
            await self.session.start()
            await self.show_history(self.session.harness.messages)
            self.status_bar.set_status("Idle")
            self.update_token_display()
        except Exception as e:
            self.status_bar.set_status("Error")
            self.notify(f"Failed to load session: {e}", severity="error")

    def action_cancel_run(self) -> None:
        """Cancel current execution on escape press."""
        if self.session.harness.is_running:
            self.session.harness.cancel()
            self.notify("Cancellation requested", severity="warning")

    async def on_prompt_input_submitted(self, event: PromptInput.Submitted) -> None:
        """Triggered when the user submits a prompt."""
        text = event.text.strip()
        if text.startswith("/"):
            # Intercept and run slash commands
            parts = text.split()
            cmd_name = parts[0]
            args = parts[1:]

            from tyrion_coding.commands import registry
            cmd = registry.get(cmd_name)
            if cmd is not None:
                if cmd_name not in ("/clear", "/quit", "/exit", "/connect"):
                    self.set_chat_active(True)
                await cmd.handler(self, args)
            else:
                self.set_chat_active(True)
                await self.transcript_view.mount(
                    MessageWidget(
                        role="system",
                        text=f"Unknown command `{cmd_name}`. Type `/help` for a list of commands.",
                    )
                )
                self.transcript_view.scroll_end()
            return

        # Check authentication before proceeding
        provider = self.session.harness.config.provider
        api_key = getattr(getattr(provider, "_config", None), "api_key", "")
        if api_key in ("", "unauthenticated"):
            self.notify("Please connect an API key first!", severity="error")
            self.prompt_connect()
            return

        if self.session.harness.is_running:
            self.notify("An agent run is already in progress!", severity="error")
            return

        self.set_chat_active(True)
        self.run_agent_loop_worker(text)

    async def clear_transcript(self) -> None:
        """Clear all messages from the transcript view and return to welcome mode."""
        for child in list(self.transcript_view.children):
            await child.remove()
        self.set_chat_active(False)

    def update_token_display(self) -> None:
        """Recalculate current session tokens and update status bar."""
        self.status_bar.set_tokens(
            self.session.context_tokens(), self.session.context_limit()
        )

    def warn_if_unknown_model(self, model: str) -> None:
        """Tell the user when we have no context-window data for the model."""
        from tyrion_coding.context_window import unknown_model_notice

        notice = unknown_model_notice(model)
        if notice:
            self.notify(notice, severity="warning", timeout=12)

    @work
    async def run_resume_worker(self, session_id: str) -> None:
        """Resumes a past session and reloads the transcript history."""
        self.status_bar.set_status("Resuming...")
        await self.clear_transcript()

        try:
            manager = SessionManager()
            storage = manager.storage_for(session_id)

            state = storage.read_state()
            target_model = state.model or self.session.harness.config.model

            from tyrion_coding.provider_config import get_provider_for_model
            provider, _, _ = get_provider_for_model(target_model, allow_unauthenticated=True)

            from tyrion_coding.session import CodingSession
            session = CodingSession(
                cwd=self.session.cwd,
                provider=provider,
                model=target_model,
                system=None,
                storage=storage,
                session_id=session_id,
                max_turns=self.session.harness.config.max_turns,
            )
            self.session = session

            await self.session.resume()

            self.status_bar.session_id = session_id
            self.status_bar.model = target_model
            self.prompt_box.set_model(target_model)
            self.warn_if_unknown_model(target_model)

            await self.show_history(self.session.harness.messages)
            self.status_bar.set_status("Idle")
            self.update_token_display()
            self.notify(f"Resumed session {session_id[:8]}...")
        except Exception as e:
            self.status_bar.set_status("Error")
            self.notify(f"Failed to resume session: {e}", severity="error")

    @work(exclusive=True)
    async def run_agent_loop_worker(self, prompt_text: str) -> None:
        """Runs the harness prompt loop inside a background worker."""
        if self.session.needs_compaction():
            await self.transcript_view.mount(
                MessageWidget(
                    "system",
                    "Context is nearly full. Compacting the conversation…"
                )
            )
            self.transcript_view.scroll_end()
            self.status_bar.set_status("Compacting")
            try:
                await self.session.compact()
                await self.clear_transcript()
                await self.init_session()
                await self.transcript_view.mount(
                    MessageWidget(
                        "system",
                        "Compaction complete."
                    )
                )
                self.transcript_view.scroll_end()
            except Exception as exc:
                self.notify(f"Automatic compaction failed: {exc}", severity="error")

        self.status_bar.set_status("Running")
        self.thinking_indicator.visible = True

        user_widget = MessageWidget("user", prompt_text)
        await self.transcript_view.mount(user_widget)
        self.transcript_view.scroll_end()
        self.update_token_display()

        assistant_widget: MessageWidget | None = None
        current_tool_widget: ToolCallWidget | None = None
        assistant_text = ""
        label_next = True  # Tyrion's name goes on the first thing it says in this run

        try:
            async for agent_event in self.session.prompt(prompt_text):
                if isinstance(agent_event, MessageUpdateEvent):
                    if isinstance(agent_event.message, AssistantMessage):
                        from tyrion_agent.provider_events import (
                            TextDeltaEvent,
                            ThinkingDeltaEvent,
                        )

                        inner_event = agent_event.assistant_message_event
                        if isinstance(inner_event, TextDeltaEvent):
                            self.thinking_indicator.visible = False
                            if assistant_widget is None:
                                assistant_widget = MessageWidget(
                                    "assistant", "", show_label=label_next
                                )
                                label_next = False
                                await self.transcript_view.mount(assistant_widget)
                            assistant_text += inner_event.delta
                            assistant_widget.update_content(assistant_text)
                            self.transcript_view.scroll_end()

                        elif isinstance(inner_event, ThinkingDeltaEvent):
                            pass

                elif isinstance(agent_event, MessageEndEvent):
                    if isinstance(agent_event.message, AssistantMessage):
                        if getattr(agent_event.message, "stop_reason", None) == "error":
                            error_text = agent_event.message.error_message or "Unknown API error"
                            await self.transcript_view.mount(
                                MessageWidget("error", f"API Error: {error_text}")
                            )
                        assistant_widget = None
                        assistant_text = ""
                        self.transcript_view.scroll_end()

                elif isinstance(agent_event, ToolExecutionStartEvent):
                    self.thinking_indicator.visible = False
                    current_tool_widget = ToolCallWidget(
                        agent_event.tool_name, agent_event.args, live=True
                    )
                    await self.transcript_view.mount(current_tool_widget)
                    self.transcript_view.scroll_end()

                elif isinstance(agent_event, ToolExecutionEndEvent):
                    if current_tool_widget is not None:
                        current_tool_widget.set_result(
                            agent_event.result.text, agent_event.is_error
                        )
                    current_tool_widget = None
                    self.thinking_indicator.visible = True  # the model reads the result next
                    self.transcript_view.scroll_end()

        except Exception as e:
            await self.transcript_view.mount(
                MessageWidget("error", f"App Error: {e}")
            )
            self.transcript_view.scroll_end()
        finally:
            self.thinking_indicator.visible = False
            self.status_bar.set_status("Idle")
            self.update_token_display()
            self.prompt_input.focus()
