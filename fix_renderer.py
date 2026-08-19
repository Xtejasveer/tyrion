import re

with open("src/tyrion_coding/rendering.py", "r") as f:
    code = f.read()

# Add printing for errors in MessageEndEvent
new_code = code.replace(
    "        elif isinstance(event, MessageEndEvent):",
    """        elif isinstance(event, MessageEndEvent):
            if isinstance(event.message, AssistantMessage) and getattr(event.message, "stop_reason", None) == "error":
                self.console.print(Panel(event.message.error_message or "Unknown error", title="❌ API Error", border_style="red"))"""
)

with open("src/tyrion_coding/rendering.py", "w") as f:
    f.write(new_code)
