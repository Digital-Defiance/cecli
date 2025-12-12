"""Output widget for Aider TUI using Textual's Markdown widget."""

import re

from textual.containers import VerticalScroll
from textual.message import Message
from textual.widgets import Markdown, Static


class CostUpdate(Message):
    """Message to update cost in footer."""

    def __init__(self, cost: float):
        self.cost = cost
        super().__init__()


class OutputContainer(VerticalScroll):
    """Scrollable output area using Markdown widgets for rich rendering.

    Uses Textual's native Markdown widget with MarkdownStream for
    efficient streaming of LLM responses.
    """

    DEFAULT_CSS = """
    OutputContainer {
        scrollbar-gutter: stable;
        background: $background;
    }

    OutputContainer > Markdown {
        margin: 0 1;
        padding: 0;
        background: $background;
    }

    OutputContainer > .user-message {
        margin: 1 1 0 1;
        padding: 0;
        color: $primary;
        background: $background;
    }

    OutputContainer > .system-message {
        margin: 0 1;
        padding: 0;
        color: $secondary;
        background: $background;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._current_markdown: Markdown | None = None
        self._stream = None
        self._buffer = ""

    async def start_response(self):
        """Start a new LLM response section with streaming support."""
        # Stop any existing stream
        await self._stop_stream()

        # Create new Markdown widget for this response
        self._current_markdown = Markdown("", id=f"response-{len(self.children)}")
        await self.mount(self._current_markdown)

        # Create stream for efficient updates
        self._stream = Markdown.get_stream(self._current_markdown)
        self._buffer = ""

        # Keep scrolled to bottom
        self.anchor()

    async def stream_chunk(self, text: str):
        """Stream a chunk of markdown text."""
        if not text:
            return

        # Check for cost updates in the text
        self._check_cost(text)

        if self._stream:
            # Use MarkdownStream for efficient batched updates
            await self._stream.write(text)
        elif self._current_markdown:
            # Fallback: append to buffer and update
            self._buffer += text
            await self._current_markdown.update(self._buffer)
        else:
            # No active response - start one
            await self.start_response()
            await self.stream_chunk(text)

    async def end_response(self):
        """End the current LLM response."""
        await self._stop_stream()

    async def _stop_stream(self):
        """Stop the current markdown stream."""
        if self._stream:
            try:
                await self._stream.stop()
            except Exception:
                pass
            self._stream = None

    def add_user_message(self, text: str):
        """Add a user message (displayed differently from LLM output)."""
        # User messages shown with > prefix, markup disabled to avoid parsing issues
        static = Static(f"> {text}", classes="user-message", markup=False)
        self.mount(static)
        self.scroll_end(animate=False)

    def add_system_message(self, text: str):
        """Add a system/tool message."""
        if not text.strip():
            return

        # Strip ANSI codes
        text = re.sub(r'\x1b\[[0-9;]*m', '', text)
        # Strip Rich markup tags like [blue], [/bold], etc.
        text = re.sub(r'\[/?[a-zA-Z0-9_ #/]+\]', '', text)

        if not text.strip():
            return

        # Create Static with markup disabled to avoid Rich parsing issues
        static = Static(text, classes="system-message", markup=False)
        self.mount(static)
        self.scroll_end(animate=False)

    def add_output(self, text: str, task_id: str = None):
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
        self.add_system_message(text)

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
        static = Static(f"\n{title}", classes="system-message", markup=False)
        self.mount(static)
        self.scroll_end(animate=False)

    def clear_output(self):
        """Clear all output."""
        self._current_markdown = None
        self._stream = None
        self._buffer = ""
        self.remove_children()
