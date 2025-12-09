"""Widgets for the Aider TUI."""

from .completion_bar import CompletionBar
from .footer import AiderFooter
from .input_area import InputArea
from .output import OutputContainer
from .status_bar import StatusBar

__all__ = [
    "AiderFooter",
    "CompletionBar",
    "InputArea",
    "OutputContainer",
    "StatusBar",
]
