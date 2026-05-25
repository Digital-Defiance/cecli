"""
Headless I/O that emits structured events for web/API consumers.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from typing import Any, Callable, TextIO

from rich.console import Console

from cecli.io import InputOutput


class EventIO(InputOutput):
    """
    InputOutput that records tool/assistant activity as JSON-serializable events.

    Token streaming is emitted by :meth:`Session.run_message` (not here) so chunks
    are not duplicated to stdout.
    """

    def __init__(
        self,
        on_event: Callable[[dict[str, Any]], None] | None = None,
        echo_to_console: bool = False,
        **kwargs,
    ):
        kwargs.setdefault("fancy_input", False)
        kwargs.setdefault("pretty", False)
        self.on_event = on_event
        self.echo_to_console = echo_to_console
        self.events: list[dict[str, Any]] = []
        self._confirm_lock = threading.Lock()
        self._confirm_events: dict[str, threading.Event] = {}
        self._confirm_answers: dict[str, bool] = {}
        self._confirm_timeout_s = 3600.0
        self._null_sink: TextIO | None = None
        if not echo_to_console and kwargs.get("output") is None:
            self._null_sink = open(os.devnull, "w", encoding="utf-8")
            kwargs["output"] = self._null_sink
        super().__init__(**kwargs)
        sink = self.output if self.output is not None else self._null_sink
        if sink is None:
            self._null_sink = open(os.devnull, "w", encoding="utf-8")
            sink = self._null_sink
            self.output = sink
        # InputOutput attaches Console to stdout; when the desktop app spawns core with
        # stdout closed, Rich writes raise BrokenPipeError.
        self.console = Console(file=sink, force_terminal=False, no_color=True)

    def emit(self, event_type: str, **payload: Any) -> dict[str, Any]:
        event = {"type": event_type, **payload}
        self.events.append(event)
        if self.on_event:
            self.on_event(event)
        return event

    def emit_progress(
        self,
        *,
        label: str,
        current: int | None = None,
        total: int | None = None,
        message: str | None = None,
        fraction: float | None = None,
    ) -> dict[str, Any]:
        from bright_vision_core.gui_progress import emit_progress

        emit_progress(
            self,
            label=label,
            current=current,
            total=total,
            message=message,
            fraction=fraction,
        )
        return self.events[-1] if self.events else {"type": "progress", "label": label}

    def drain_events(self) -> list[dict[str, Any]]:
        events = self.events
        self.events = []
        return events

    def write_event_line(self, event: dict[str, Any]) -> None:
        """Write one JSON line to ``self.output`` (for subprocess workers)."""
        line = json.dumps(event, ensure_ascii=False) + "\n"
        if self.output:
            self.output.write(line)
            self.output.flush()
        elif self.echo_to_console:
            print(line, end="")

    def tool_output(self, *messages, log_only=False, bold=False, **kwargs):
        kwargs.pop("coder_uuid", None)
        if not log_only:
            text = " ".join(str(m) for m in messages)
            self.emit("tool_output", text=text)
        if self.echo_to_console:
            super().tool_output(*messages, log_only=log_only, bold=bold, **kwargs)

    def tool_error(self, message="", strip=True, **kwargs):
        kwargs.pop("coder_uuid", None)
        self.emit("tool_error", text=str(message))
        if self.echo_to_console:
            super().tool_error(message, strip=strip, **kwargs)

    def tool_warning(self, message="", strip=True, **kwargs):
        kwargs.pop("coder_uuid", None)
        self.emit("tool_warning", text=str(message))
        if self.echo_to_console:
            super().tool_warning(message, strip=strip, **kwargs)

    def resolve_confirm(self, confirm_id: str, accepted: bool) -> bool:
        """Answer a pending confirm (HTTP/UI). Returns False if unknown or already resolved."""
        with self._confirm_lock:
            event = self._confirm_events.get(confirm_id)
            if event is None:
                return False
            self._confirm_answers[confirm_id] = accepted
            event.set()
        return True

    def confirm_ask(self, question, subject=None, explicit_yes=None, group=None, allow_never=False):
        default = explicit_yes if explicit_yes is not None else bool(self.yes)
        if self.yes:
            self.emit(
                "confirm",
                confirm_id=None,
                question=str(question),
                subject=subject,
                default=default,
                auto_answered=True,
            )
            return True

        confirm_id = uuid.uuid4().hex
        waiter = threading.Event()
        with self._confirm_lock:
            self._confirm_events[confirm_id] = waiter

        self.emit(
            "confirm",
            confirm_id=confirm_id,
            question=str(question),
            subject=subject,
            default=default,
            auto_answered=False,
        )

        if not waiter.wait(timeout=self._confirm_timeout_s):
            with self._confirm_lock:
                self._confirm_events.pop(confirm_id, None)
                self._confirm_answers.pop(confirm_id, None)
            return False

        with self._confirm_lock:
            self._confirm_events.pop(confirm_id, None)
            answer = self._confirm_answers.pop(confirm_id, False)
        return answer

    def get_input(self, root, rel_fnames, addable_rel_fnames, commands, abs_read_only_fnames, edit_format=""):
        raise RuntimeError(
            "EventIO does not support interactive input; send messages via Session.run_message()."
        )

    def _tool_message(self, message="", strip=True, color=None):
        if self.echo_to_console:
            try:
                super()._tool_message(message, strip, color)
            except BrokenPipeError:
                pass

    def print(self, message=""):
        if self.echo_to_console:
            try:
                super().print(message)
            except BrokenPipeError:
                pass

    def ai_output(self, content):
        self.emit("assistant_complete", text=content or "")
        if self.echo_to_console:
            try:
                super().ai_output(content)
            except BrokenPipeError:
                pass
