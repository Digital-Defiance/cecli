from textual.containers import Horizontal
from textual.widgets import Static


class KeyHints(Horizontal):
    """Key hints widget with left sub-panel and right hints."""

    DEFAULT_CSS = """
    KeyHints {
        color: $secondary;
        height: 1;
        width: 100%;
        padding: 0 2 0 2;
        margin: 0 0 1 0;
    }

    KeyHints > .key-hints-left {
        color: $secondary;
        width: auto;
    }

    KeyHints > .key-hints-right {
        text-align: right;
        color: $secondary;
        width: 1fr;
    }
    """

    DEFAULT_LEFT_TEXT = "/commands • @path/to/file"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.left_panel = Static(self.DEFAULT_LEFT_TEXT, classes="key-hints-left")
        self.right_panel = Static("", classes="key-hints-right")

    def compose(self):
        yield self.left_panel
        yield self.right_panel

    def update_left(self, text: str):
        """Update the left sub-panel text, limiting to 96 chars with ellipses."""
        if len(text) > 96:
            text = text[:93] + "..."
        self.left_panel.update(text)

    def update_right(self, text: str):
        """Update the right hints text."""
        self.right_panel.update(text)

    def update(self, text: str):
        """Update the right hints text (backward compatibility)."""
        self.update_right(text)
