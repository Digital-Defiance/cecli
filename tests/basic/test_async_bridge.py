"""async_bridge: loop-bound primitives and threaded async iteration."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from bright_vision_core.async_bridge import (
    HEARTBEAT_PULSE,
    iterate_async_with_heartbeats,
    rebind_coder_loop_primitives,
    run,
)


class _FakeIO:
    def __init__(self) -> None:
        self.events: list[object] = []


def test_rebind_coder_loop_primitives_updates_linter() -> None:
    coder = SimpleNamespace(
        interrupt_event=asyncio.Event(),
        linter=SimpleNamespace(interrupt_event=None),
    )
    coder.linter.interrupt_event = coder.interrupt_event

    async def _touch_event() -> None:
        await asyncio.sleep(0)

    asyncio.run(_touch_event())

    rebind_coder_loop_primitives(coder)
    assert coder.linter.interrupt_event is coder.interrupt_event

    async def _wait_on_rebound() -> None:
        coder.interrupt_event.set()
        await coder.interrupt_event.wait()

    asyncio.run(_wait_on_rebound())


def test_iterate_async_with_heartbeats_rebinds_coder_event() -> None:
    async def _bind_coder() -> SimpleNamespace:
        ev = asyncio.Event()
        await asyncio.sleep(0)
        linter = SimpleNamespace(interrupt_event=ev)
        return SimpleNamespace(interrupt_event=ev, linter=linter)

    coder = asyncio.run(_bind_coder())

    async def _agen():
        coder.interrupt_event.set()
        await coder.interrupt_event.wait()
        yield "ok"

    pieces = [
        p
        for p in iterate_async_with_heartbeats(
            _agen,
            _FakeIO(),
            coder=coder,
            interval_s=0.01,
        )
        if p is not HEARTBEAT_PULSE
    ]
    assert pieces == ["ok"]


def test_run_helper_still_works() -> None:
    async def _coro() -> int:
        return 42

    assert run(_coro()) == 42
