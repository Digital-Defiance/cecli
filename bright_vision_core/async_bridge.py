"""Run cecli async APIs from sync HTTP/session code."""

from __future__ import annotations

import asyncio
import queue
import threading
from collections.abc import AsyncIterator, Callable, Coroutine, Iterator
from typing import Any, TypeVar

T = TypeVar("T")


def rebind_coder_loop_primitives(coder: Any) -> None:
    """
    Replace asyncio primitives that were bound to a closed event loop.

    Headless sessions call ``asyncio.run()`` for setup/preproc, then stream
    ``send_message`` on a dedicated loop in a worker thread. Reusing the same
    ``asyncio.Event`` across those loops raises "bound to a different event loop".
    """
    coder.interrupt_event = asyncio.Event()
    linter = getattr(coder, "linter", None)
    if linter is not None:
        linter.interrupt_event = coder.interrupt_event

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
    make_agen: Callable[[], AsyncIterator[T]],
    io: Any,
    *,
    coder: Any | None = None,
    label: str = "LLM",
    message: str = "Waiting for model response…",
    interval_s: float = 8.0,
) -> Iterator[T | object]:
    """
    Bridge an async iterator and emit ``progress`` events while blocked on the next chunk.

    ``make_agen`` is invoked inside the worker loop (not on the caller thread) so async
    generators and ``asyncio.Event`` on ``coder`` are created/bound to that loop.

    Yields :data:`HEARTBEAT_PULSE` between pulses so callers flush ``io.events`` to SSE.
    """
    from bright_vision_core.gui_progress import emit_progress

    out: queue.Queue[Any] = queue.Queue()

    def producer() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:

            async def consume() -> None:
                if coder is not None:
                    rebind_coder_loop_primitives(coder)
                agen = make_agen()
                async for item in agen:
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
