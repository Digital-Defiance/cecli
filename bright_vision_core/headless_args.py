"""Minimal argparse-like namespace for headless Vision sessions."""

from __future__ import annotations

from types import SimpleNamespace


def default_headless_args(*, yes: bool = False) -> SimpleNamespace:
    """Defaults for ``Coder.create`` when no CLI ``args`` object exists."""
    return SimpleNamespace(
        debug=False,
        tui=False,
        yes=yes,
        yes_always_commands=False,
        fancy_input=False,
        show_speed=False,
        max_reflections=3,
        custom="{}",
        file_diffs=True,
        cost_limit=float("inf"),
        disable_scraping=True,
        use_enhanced_map=False,
    )
