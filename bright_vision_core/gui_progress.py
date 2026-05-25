"""
Progress reporting for Aider Vision (headless / GUI).

Replaces terminal tqdm bars with structured ``progress`` events on EventIO.
"""

from __future__ import annotations

import os
from typing import Any, Callable, Iterable, Iterator, TypeVar

T = TypeVar("T")


def headless_enabled() -> bool:
    from bright_vision_core.headless_stdio import headless_enabled as _headless_enabled

    return _headless_enabled()


def emit_progress(
    io: Any,
    *,
    label: str,
    current: int | None = None,
    total: int | None = None,
    message: str | None = None,
    fraction: float | None = None,
) -> None:
    if io is None:
        return
    emit = getattr(io, "emit", None)
    if not callable(emit):
        return
    if fraction is None and current is not None and total:
        fraction = max(0.0, min(1.0, current / total))
    payload: dict[str, Any] = {"label": label}
    if current is not None:
        payload["current"] = current
    if total is not None:
        payload["total"] = total
    if fraction is not None:
        payload["fraction"] = fraction
    if message is not None:
        payload["message"] = message
    elif current is not None and total is not None:
        payload["message"] = f"{current}/{total}"
    emit("progress", **payload)


def should_use_gui_progress(io: Any) -> bool:
    if io is None:
        return headless_enabled()
    if headless_enabled():
        return True
    return callable(getattr(io, "emit", None))


def progress_iter(
    iterable: Iterable[T],
    *,
    desc: str = "Working",
    io: Any = None,
    total: int | None = None,
    min_items_for_bar: int = 100,
) -> Iterator[T]:
    """
    Iterate with tqdm in the CLI, or ``progress`` events for Vision / EventIO.
    """
    if total is None:
        try:
            total = len(iterable)  # type: ignore[arg-type]
        except TypeError:
            total = None

    use_gui = should_use_gui_progress(io)

    if use_gui and io is not None:
        throttle = max(1, (total or 1) // 80)
        for i, item in enumerate(iterable, start=1):
            if total is None or i == 1 or i >= total or i % throttle == 0:
                emit_progress(io, label=desc, current=i, total=total)
            yield item
        if total is not None:
            emit_progress(io, label=desc, current=total, total=total)
        return

    if not use_gui and total is not None and total > min_items_for_bar:
        from tqdm import tqdm

        yield from tqdm(iterable, desc=desc, total=total)
        return

    yield from iterable
