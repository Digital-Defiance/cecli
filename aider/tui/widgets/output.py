"""Output widgets for Aider TUI."""

import re
from io import StringIO

from rich.console import Console
from rich.text import Text
from textual.message import Message
from textual.widgets import RichLog


class CostUpdate(Message):
    """Message to update cost in footer."""

    def __init__(self, cost: float):
        self.cost = cost
        super().__init__()


class OutputContainer(RichLog):
    """Single scrollable output area."""

    def __init__(self, **kwargs):
        """Initialize output container."""
        super().__init__(auto_scroll=True, wrap=True, markup=True, **kwargs)
    def start_task(self, task_id: str, title: str, task_type: str = "general"):
        """Start a new task section (visual separator)."""
        self._flush_buffer()
        self.write(Text(f"\n─── {title} ───", style="dim"))

    def add_output(self, text: str, task_id: str = None):
        """Add output text with intelligent whitespace handling."""
        if not text:
            return
        
        # Clean up the text first
        text = self._normalize_whitespace(text)
        text = self._format_markdown(text)
        text = self._format_code_blocks(text)
        text = self._format_message_type(text)
        
        # Buffer for complete lines
        self._stream_buffer += text
        
        # Only flush complete lines (RichLog.write adds newline after each call)
        while '\n' in self._stream_buffer:
            line, self._stream_buffer = self._stream_buffer.split('\n', 1)
            self._write_line(line)
class CostUpdate(Message):
    """Message to update cost in footer."""

    def __init__(self, cost: float):
        self.cost = cost
        super().__init__()


class OutputContainer(RichLog):
    """Single scrollable output area."""

    def __init__(self, **kwargs):
        """Initialize output container."""
        super().__init__(auto_scroll=True, wrap=True, markup=True, **kwargs)
        self._stream_buffer = ""

    def start_task(self, task_id: str, title: str, task_type: str = "general"):
        """Start a new task section (visual separator)."""
        self._flush_buffer()
        self.write(Text(f"\n─── {title} ───", style="dim"))

    def add_output(self, text: str, task_id: str = None):
        """Add output text, buffering for complete lines."""
        if not text:
            return

        self._stream_buffer += text

        # Only flush complete lines (RichLog.write adds newline after each call)
        while '\n' in self._stream_buffer:
            line, self._stream_buffer = self._stream_buffer.split('\n', 1)
            self._write_line(line)

    def _flush_buffer(self):
        """Flush any remaining buffered content."""
        if self._stream_buffer:
            self._write_line(self._stream_buffer)
            self._stream_buffer = ""

    def _write_line(self, text: str):
        """Write a single line to the display."""
        if not text:
            return

        # Check for cost information and emit update
        self._check_for_cost(text)

        # Strip Rich markup tags like [blue], [/], [bold], etc.
        text = self._strip_rich_markup(text)

        # Handle ANSI codes first
        if '\x1b' in text:
            self.write(Text.from_ansi(text))
            return

        # Try to render as markdown for formatting
        if self._has_markdown(text):
            try:
                from rich.markdown import Markdown
                width = max(self.size.width - 2, 40)
                console = Console(file=StringIO(), force_terminal=True, width=width)
                md = Markdown(text)
                with console.capture() as capture:
                    console.print(md, end="")
                rendered = capture.get().rstrip('\n')
                if rendered:
                    self.write(Text.from_ansi(rendered))
                    return
            except Exception:
                pass

        # Fallback to plain text
        self.write(Text(text))

    def _has_markdown(self, text: str) -> bool:
        """Check if text has markdown formatting."""
        # Look for common markdown patterns
        patterns = ['**', '__', '`', '```', '##', '- ', '* ', '1. ']
        return any(p in text for p in patterns)

    def _check_for_cost(self, text: str):
        """Check for cost info and post message to update footer."""
        # Look for pattern like "$0.0086 session" or "$X.XX session"
        match = re.search(r'\$(\d+\.?\d*)\s*session', text)
        if match:
            try:
                cost = float(match.group(1))
                self.post_message(CostUpdate(cost))
            except (ValueError, AttributeError):
                pass

    def _strip_rich_markup(self, text: str) -> str:
        """Remove Rich console markup tags from text."""
        # Pattern matches [tagname] and [/tagname] and [/]
        # Common tags: [blue], [bold], [red], [green], [/], [/blue], etc.
        pattern = r'\[/?(?:blue|red|green|yellow|bold|dim|italic|underline|strike|reverse|blink|/)*\]'
        return re.sub(pattern, '', text)

    def add_markdown(self, text: str):
        """Add markdown content (renders via Rich)."""
        self._flush_buffer()
        try:
            console = Console(file=StringIO(), force_terminal=True, width=self.size.width - 4)
            from rich.markdown import Markdown
            md = Markdown(text)
            with console.capture() as capture:
                console.print(md)
            rendered = capture.get()
            self.write(Text.from_ansi(rendered))
        except Exception:
            self.write(Text(text))

    def clear_output(self):
        """Clear all output."""
        self._stream_buffer = ""
        self.clear()