"""Input widget for Aider TUI."""

from prompt_toolkit.history import FileHistory
from textual.message import Message
from textual.widgets import Input


class InputArea(Input):
    """Input widget with autocomplete and history support."""

    class CompletionRequested(Message):
        """User requested completion (Tab key or auto-trigger)."""

        def __init__(self, text: str):
            self.text = text
            super().__init__()

    class CompletionCycle(Message):
        """User wants to cycle through completions."""
        pass

    class CompletionAccept(Message):
        """User wants to accept current completion."""
        pass

    class CompletionDismiss(Message):
        """User wants to dismiss completions."""
        pass

    def __init__(self, history_file: str = None, **kwargs):
        """Initialize input area.

        Args:
            history_file: Path to input history file for up/down navigation
        """
        super().__init__(
            placeholder="> Type your message...",
            **kwargs
        )
        self.files = []
        self.commands = []
        self.completion_active = False

        # History support - lazy loaded
        self.history_file = history_file
        self._history: list[str] | None = None  # None = not loaded yet
        self._history_index = -1  # -1 = not navigating, 0+ = position in history
        self._saved_input = ""  # Saves current input when navigating history

    def _ensure_history_loaded(self) -> list[str]:
        """Lazily load history on first access.

        Returns history with most recent at the end (index -1).
        """
        if self._history is None:
            self._history = []
            if self.history_file:
                try:
                    # FileHistory returns most recent first, so reverse it
                    self._history = list(reversed(list(FileHistory(self.history_file).load_history_strings())))
                except (OSError, IOError):
                    pass  # History file doesn't exist yet or can't be read
        return self._history

    def update_autocomplete_data(self, files, commands):
        """Update autocomplete suggestions.

        Args:
            files: List of file paths for autocomplete
            commands: List of command names for autocomplete
        """
        self.files = files
        self.commands = commands

    def save_to_history(self, text: str) -> None:
        """Save input to history file and in-memory list.

        Args:
            text: The input text to save
        """
        # Skip empty, whitespace-only, or very short inputs
        if not text or not text.strip() or len(text.strip()) <= 1:
            return

        # Skip if same as last history entry
        history = self._ensure_history_loaded()
        if history and history[-1] == text:
            return

        # Save to file
        if self.history_file:
            try:
                FileHistory(self.history_file).append_string(text)
            except (OSError, IOError):
                pass

        # Add to in-memory history
        history.append(text)

        # Reset navigation state
        self._history_index = -1
        self._saved_input = ""

    def _history_prev(self) -> None:
        """Navigate to previous (older) history entry."""
        history = self._ensure_history_loaded()
        if not history:
            return

        # Save current input when first entering history
        if self._history_index == -1:
            self._saved_input = self.value
            self._history_index = len(history) - 1
        elif self._history_index > 0:
            self._history_index -= 1
        else:
            return  # Already at oldest

        self.value = history[self._history_index]
        self.cursor_position = len(self.value)

    def _history_next(self) -> None:
        """Navigate to next (newer) history entry."""
        if self._history_index == -1:
            return  # Not navigating history

        history = self._ensure_history_loaded()
        if self._history_index < len(history) - 1:
            self._history_index += 1
            self.value = history[self._history_index]
        else:
            # Back to current input
            self._history_index = -1
            self.value = self._saved_input

        self.cursor_position = len(self.value)

    def on_key(self, event) -> None:
        """Handle keys for completion and history navigation."""
        if self.disabled:
            return

        if event.key == "tab":
            event.stop()
            event.prevent_default()
            if self.completion_active:
                # Cycle through completions
                self.post_message(self.CompletionCycle())
            else:
                # Request completions
                self.post_message(self.CompletionRequested(self.value))
        elif event.key == "escape" and self.completion_active:
            event.stop()
            event.prevent_default()
            self.post_message(self.CompletionDismiss())
        elif event.key == "up":
            # Navigate to previous history entry
            event.stop()
            event.prevent_default()
            self._history_prev()
        elif event.key == "down":
            # Navigate to next history entry
            event.stop()
            event.prevent_default()
            self._history_next()

    def on_input_changed(self, event) -> None:
        """Update completions as user types."""
        if not self.disabled:
            # Auto-trigger for slash commands, @ symbols, or update existing completions
            if event.value.startswith("/") or "@" in event.value or self.completion_active:
                self.post_message(self.CompletionRequested(event.value))

    def on_input_submitted(self, event) -> None:
        """Handle Enter key - accept completion if active."""
        if self.completion_active:
            # Let app handle accepting completion
            self.post_message(self.CompletionAccept())
            # Prevent the default submit behavior
            event.stop()
            event.prevent_default()
