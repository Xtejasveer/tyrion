from __future__ import annotations

from typing import TYPE_CHECKING
from textual import work
from textual.app import App, ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Header

from tyrion_agent.events import (
    MessageEndEvent,
    MessageUpdateEvent,
    ToolExecutionEndEvent,
    ToolExecutionStartEvent,
)
from tyrion_agent.messages import AssistantMessage
from tyrion_coding.tui.widgets import (
    MessageWidget,
    PromptInput,
    ThinkingIndicator,
    ToolCallWidget,
    TUIStatusBar,
)

if TYPE_CHECKING:
    from tyrion_coding.session import CodingSession


class TyrionApp(App[None]):
    """Tyrion Interactive Terminal User Interface."""

    CSS = """
    TyrionApp {
        background: $background;
    }

    #transcript-container {
        height: 1fr;
        border: none;
        padding: 1 2;
    }

    PromptInput {
        height: 6;
        margin: 1 2;
        border: tall $primary;
    }

    #thinking {
        margin: 0 2;
        height: 1;
    }

    TUIStatusBar {
        dock: bottom;
        height: 1;
        background: $surface;
        color: $text;
    }
    """

    BINDINGS = [
        ("escape", "cancel_run", "Cancel execution"),
        ("ctrl+c", "quit", "Quit"),
    ]

    def __init__(self, session: CodingSession) -> None:
        super().__init__()
        self.session = session

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield VerticalScroll(id="transcript-container")
        yield ThinkingIndicator(id="thinking")
        yield PromptInput(placeholder="Type your prompt here... (Enter to submit, Shift+Enter for newline)")
        yield TUIStatusBar(
            session_id=self.session.session_id,
            model=self.session.harness.config.model,
            cwd=str(self.session.cwd),
        )

    def on_mount(self) -> None:
        """Actions to run when screen mounts."""
        self.transcript_view = self.query_one("#transcript-container", VerticalScroll)
        self.thinking_indicator = self.query_one("#thinking", ThinkingIndicator)
        self.prompt_input = self.query_one(PromptInput)
        self.status_bar = self.query_one(TUIStatusBar)
        self.prompt_input.focus()
        self.init_session()

    @work
    async def init_session(self) -> None:
        """Initialize the session and load conversation history."""
        self.status_bar.set_status("Initializing...")
        try:
            await self.session.start()

            from tyrion_agent.messages import (
                AssistantMessage,
                ToolResultMessage,
                UserMessage,
            )

            messages = self.session.harness.messages
            i = 0
            while i < len(messages):
                msg = messages[i]
                if isinstance(msg, UserMessage):
                    await self.transcript_view.mount(
                        MessageWidget("user", msg.content)
                    )
                elif isinstance(msg, AssistantMessage):
                    if msg.text:
                        await self.transcript_view.mount(
                            MessageWidget("assistant", msg.text)
                        )
                    for tool_call in msg.tool_calls:
                        tool_result_msg = None
                        for j in range(i + 1, len(messages)):
                            if (
                                isinstance(messages[j], ToolResultMessage)
                                and messages[j].tool_call_id == tool_call.id
                            ):
                                tool_result_msg = messages[j]
                                break

                        tool_widget = ToolCallWidget(
                            tool_call.name, tool_call.arguments
                        )
                        if tool_result_msg is not None:
                            tool_widget.set_result(
                                tool_result_msg.text, tool_result_msg.is_error
                            )
                        await self.transcript_view.mount(tool_widget)
                i += 1

            self.transcript_view.scroll_end()
            self.status_bar.set_status("Idle")
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
        if self.session.harness.is_running:
            self.notify("An agent run is already in progress!", severity="error")
            return

        self.run_agent_loop_worker(event.text)

    @work(exclusive=True)
    async def run_agent_loop_worker(self, prompt_text: str) -> None:
        """Runs the harness prompt loop inside a background worker."""
        self.status_bar.set_status("Running")
        self.thinking_indicator.visible = True

        # Append User Message to UI
        user_widget = MessageWidget("user", prompt_text)
        await self.transcript_view.mount(user_widget)
        self.transcript_view.scroll_end()

        assistant_widget: MessageWidget | None = None
        current_tool_widget: ToolCallWidget | None = None
        assistant_text = ""

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
                                assistant_widget = MessageWidget("assistant", "")
                                await self.transcript_view.mount(assistant_widget)
                            assistant_text += inner_event.delta
                            assistant_widget.update_content(assistant_text)
                            self.transcript_view.scroll_end()

                        elif isinstance(inner_event, ThinkingDeltaEvent):
                            # Streaming reasoning, currently ignored in rendering
                            pass

                elif isinstance(agent_event, MessageEndEvent):
                    if isinstance(agent_event.message, AssistantMessage):
                        if getattr(agent_event.message, "stop_reason", None) == "error":
                            error_text = agent_event.message.error_message or "Unknown API error"
                            await self.transcript_view.mount(
                                MessageWidget("error", f"❌ API Error: {error_text}")
                            )
                        assistant_widget = None
                        assistant_text = ""
                        self.transcript_view.scroll_end()

                elif isinstance(agent_event, ToolExecutionStartEvent):
                    self.thinking_indicator.visible = False
                    current_tool_widget = ToolCallWidget(
                        agent_event.tool_name, agent_event.args
                    )
                    await self.transcript_view.mount(current_tool_widget)
                    self.transcript_view.scroll_end()

                elif isinstance(agent_event, ToolExecutionEndEvent):
                    if current_tool_widget is not None:
                        current_tool_widget.set_result(
                            agent_event.result.text, agent_event.is_error
                        )
                    current_tool_widget = None
                    self.transcript_view.scroll_end()

        except Exception as e:
            await self.transcript_view.mount(
                MessageWidget("error", f"💥 App Error: {str(e)}")
            )
            self.transcript_view.scroll_end()
        finally:
            self.thinking_indicator.visible = False
            self.status_bar.set_status("Idle")
            self.prompt_input.focus()