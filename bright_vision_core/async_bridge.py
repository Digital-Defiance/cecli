"""Run cecli async APIs from sync HTTP/session code."""

from __future__ import annotations

import asyncio
import queue
import threading
from collections.abc import AsyncIterator, Coroutine, Iterator
from typing import Any, TypeVar

T = TypeVar("T")

_DONE = object()
# Yielded to the sync iterator so Session.run_message can flush io.events to SSE.
HEARTBEAT_PULSE = object()


def run(coro: Coroutine[object, object, T]) -> T:
    """Run one coroutine in a fresh event loop (sync callers only)."""
    return asyncio.run(coro)


def iterate_async(agen: AsyncIterator[T]) -> Iterator[T]:
    """Bridge an async generator to a sync iterator (one loop per call)."""
    loop = asyncio.new_event_loop()
    try:
        ait = agen.__aiter__()

        def _next() -> T:
            return loop.run_until_complete(ait.__anext__())

        while True:
            try:
                yield _next()
            except StopAsyncIteration:
                break
    finally:
        loop.close()


def iterate_async_with_heartbeats(
    agen: AsyncIterator[T],
    io: Any,
    *,
    label: str = "LLM",
    message: str = "Waiting for model response…",
    interval_s: float = 8.0,
) -> Iterator[T | object]:
    """
    Bridge an async iterator and emit ``progress`` events while blocked on the next chunk.

    Yields :data:`HEARTBEAT_PULSE` between pulses so callers flush ``io.events`` to SSE.
    """
    from bright_vision_core.gui_progress import emit_progress

    out: queue.Queue[Any] = queue.Queue()

    def producer() -> None:
        loop = asyncio.new_event_loop()
        try:
            ait = agen.__aiter__()

            async def consume() -> None:
                async for item in ait:
                    out.put(item)

            loop.run_until_complete(consume())
            out.put(_DONE)
        except Exception as err:
            out.put(err)
        finally:
            loop.close()

    thread = threading.Thread(target=producer, daemon=True)
    thread.start()

    wait_s = max(2.0, interval_s)
    pulse = 0
    while True:
        try:
            item = out.get(timeout=wait_s)
        except queue.Empty:
            pulse += 1
            emit_progress(
                io,
                label=label,
                message=f"{message} ({int(pulse * wait_s)}s)",
            )
            yield HEARTBEAT_PULSE
            continue
        if item is _DONE:
            break
        if isinstance(item, Exception):
            raise item
        yield item

    thread.join(timeout=0.1)
