"""Tests for headless slash-command signal handling."""

from __future__ import annotations

from cecli.commands import SwitchCoderSignal

from bright_vision_core.slash_helpers import is_switch_coder_signal


def test_is_switch_coder_signal_direct() -> None:
    assert is_switch_coder_signal(SwitchCoderSignal(edit_format="diff"))


def test_is_switch_coder_signal_in_group() -> None:
    inner = SwitchCoderSignal(edit_format="diff")
    group = BaseExceptionGroup("task failures", [RuntimeError("x"), inner])
    assert is_switch_coder_signal(group)


def test_is_switch_coder_signal_rejects_other() -> None:
    assert not is_switch_coder_signal(ValueError("nope"))
    assert not is_switch_coder_signal(
        BaseExceptionGroup("task failures", [RuntimeError("x"), ValueError("y")])
    )
