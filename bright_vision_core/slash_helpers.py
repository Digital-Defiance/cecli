"""Headless cecli slash-command helpers."""

from __future__ import annotations

from collections.abc import Coroutine
from typing import Any, TypeVar

from cecli.commands import SwitchCoderSignal

from bright_vision_core.async_bridge import run

T = TypeVar("T")


def is_switch_coder_signal(exc: BaseException) -> bool:
    """True when *exc* is (or wraps) cecli's non-error coder refresh signal."""
    if isinstance(exc, SwitchCoderSignal):
        return True
    if isinstance(exc, BaseExceptionGroup):
        return any(is_switch_coder_signal(e) for e in exc.exceptions)
    return False


def run_slash_command_sync(coder: Any, cmd: str, args: str) -> None:
    """
    Run a cecli slash command from sync HTTP/session code.

    ``/add`` and similar commands raise :class:`SwitchCoderSignal` after success
    so the TUI can rebuild the coder; headless callers treat that as success.
    """
    try:
        run(coder.commands.execute(cmd, args, coder=coder))
    except BaseException as exc:
        if is_switch_coder_signal(exc):
            return
        raise


def run_coro_ignore_switch_coder(coro: Coroutine[object, object, T]) -> T | None:
    """Like :func:`run`, but return ``None`` when the coroutine signals a coder switch."""
    try:
        return run(coro)
    except BaseException as exc:
        if is_switch_coder_signal(exc):
            return None
        raise
