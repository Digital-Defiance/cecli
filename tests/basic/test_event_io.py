"""EventIO headless confirm compatibility with cecli."""

from __future__ import annotations

import asyncio

from bright_vision_core.event_io import EventIO


def test_confirm_ask_accepts_group_response_kwarg() -> None:
    io = EventIO(yes=True)
    assert asyncio.run(io.confirm_ask("Run tools?", group_response="Run MCP Tools")) is True
    assert io.group_responses["Run MCP Tools"] is True


def test_confirm_ask_uses_group_response_cache() -> None:
    io = EventIO(yes=False)
    io.group_responses["Run MCP Tools"] = False
    assert asyncio.run(io.confirm_ask("Run tools?", group_response="Run MCP Tools")) is False
