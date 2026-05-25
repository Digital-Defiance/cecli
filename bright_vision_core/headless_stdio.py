"""
Redirect or no-op terminal I/O when core runs under the Vision desktop spawn.
"""

from __future__ import annotations

import os
import signal
import sys
from typing import TextIO

_installed = False
_null_out: TextIO | None = None


def headless_enabled() -> bool:
    return (
        os.environ.get("BRIGHT_VISION_HEADLESS") == "1"
        or os.environ.get("AIDER_VISION_HEADLESS") == "1"
    )


def install_headless_stdio() -> None:
    global _installed, _null_out
    if _installed or not headless_enabled():
        return
    _installed = True
    if hasattr(signal, "SIGPIPE"):
        signal.signal(signal.SIGPIPE, signal.SIG_IGN)
    _null_out = open(os.devnull, "w", encoding="utf-8")
    sys.stdout = _null_out
