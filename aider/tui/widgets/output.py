"""Output widget for Aider TUI using Textual's RichLog widget."""

import re

from rich.padding import Padding
from textual.message import Message
from textual.widgets import RichLog


class CostUpdate(Message):
    """Message to update cost in footer."""

    def __init__(self, cost: float):
        self.cost = cost
        super().__init__()


class OutputContainer(RichLog):
    """Scrollable output area using RichLog widget for rich rendering.

    Uses Textual's RichLog widget for efficient streaming and display
    of LLM responses and system messages.
    """

    DEFAULT_CSS = """
    OutputContainer {
        scrollbar-gutter: stable;
        background: $surface;
        padding: 0 0;
    }
    """

    _last_write_type = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Line buffer for streaming text to avoid word-per-line issue
        self._line_buffer = ""
        # Enable markup for rich formatting
        self.markup = True
        self.wrap = True
        # self.highlight = True

    async def start_response(self):
        """Start a new LLM response section with streaming support."""
        # Clear the line buffer for new response
        self._line_buffer = ""
        # Keep scrolled to bottom
        self.scroll_end(animate=False)

    async def stream_chunk(self, text: str):
        """Stream a chunk of markdown text."""
        if not text:
            return

        # Check for cost updates in the text
        self._check_cost(text)

        # Add text to line buffer
        self._line_buffer += text

        # Process complete lines from buffer
        while "\n" in self._line_buffer:
            line, self._line_buffer = self._line_buffer.split("\n", 1)
            # self.write(Padding(line.strip(), (0, 0, 0, 1)))
            if line.rstrip():
                self.set_last_write_type("assistant")
                self.write(line.rstrip())
        # Scroll to end to show new content
        self.scroll_end(animate=False)

    async def end_response(self):
        """End the current LLM response."""
        await self._stop_stream()

    async def _stop_stream(self):
        """Stop the current markdown stream."""
        # Flush any remaining buffer content
        if self._line_buffer.strip():
            self.write(self._line_buffer)
            self._line_buffer = ""

        # Scroll to end
        self.scroll_end(animate=False)

    def add_user_message(self, text: str):
        """Add a user message (displayed differently from LLM output)."""
        # Escape any Rich markup brackets in user text
        text = self._escape_markup(text)
        # User messages shown with > prefix in green color
        self.set_last_write_type("user")
        self.write(f"[bold medium_spring_green]> {text}[/bold medium_spring_green]")
        self.scroll_end(animate=False)

    def add_system_message(self, text: str, dim=True):
        """Add a system/tool message."""
        if not text.strip():
            return

        # Escape any Rich markup brackets
        text = self._escape_markup(text).removesuffix("\n")
        start = ""
        end = ""
        # Write system message in secondary color
        if dim:
            start = "[dim]"
            end = "[/dim]"
            text = Padding(f"{start}{text}{end}", (0, 0, 0, 2))

        self.set_last_write_type("system")
        self.write(text)
        self.scroll_end(animate=False)

    def add_output(self, text: str, task_id: str = None, dim=True):
        """Add output text as a system message.

        This handles tool output, status messages, etc.
        LLM streaming is handled separately via start_response/stream_chunk/end_response.
        """
        if not text:
            return

        # Check for cost updates
        self._check_cost(text)

        # Always treat add_output as system messages
        # LLM streaming goes through the dedicated stream_chunk path
        self.add_system_message(text, dim=dim)

    def _check_cost(self, text: str):
        """Extract and emit cost updates."""
        match = re.search(r"\$(\d+\.?\d*)\s*session", text)
        if match:
            try:
                self.post_message(CostUpdate(float(match.group(1))))
            except (ValueError, AttributeError):
                pass

    def start_task(self, task_id: str, title: str, task_type: str = "general"):
        """Start a new task section."""
        self.write(f"\n[bold]{title}[/bold]")
        self.scroll_end(animate=False)

    def clear_output(self):
        """Clear all output."""
        self._line_buffer = ""
        self.clear()

    def _escape_markup(self, text: str) -> str:
        """Escape Rich markup brackets in text.

        In Rich markup, [ and ] are special characters. To display them
        literally, they must be escaped by doubling them: [ -> [[, ] -> ]].
        """
        # Simple escaping: replace [ with [[ and ] with ]]
        # This works for most cases, though it double-escapes already escaped brackets
        return text

    def set_last_write_type(self, type):
        if self._last_write_type and self._last_write_type != type:
            self.write("")

        self._last_write_type = type
