"""
Vision / headless runtime setup and guards against legacy ``aider`` rename issues.

Call :func:`configure_vision_runtime` when starting the HTTP API or any headless
session so TUI output and stale on-disk caches do not leak into the desktop GUI.
"""

from __future__ import annotations

import os
import pickle
import re
import shutil
import sqlite3
from pathlib import Path
from typing import Any

# Bump when repo-map tag cache schema or Python package name changes.
REPO_MAP_CACHE_VERSION = 5
REPO_MAP_CACHE_DIRNAME = f".aider.tags.cache.v{REPO_MAP_CACHE_VERSION}"
LEGACY_PYTHON_PACKAGE = "aider"
LEGACY_TAG_CACHE_PATTERN = re.compile(r"^\.aider\.tags\.cache\.v(\d+)$")

SQLITE_ERRORS = (sqlite3.OperationalError, sqlite3.DatabaseError, OSError)
CACHE_LOAD_ERRORS = SQLITE_ERRORS + (
    ModuleNotFoundError,
    AttributeError,
    pickle.UnpicklingError,
)

_tqdm_patched = False
_runtime_configured = False


def headless_enabled() -> bool:
    from bright_vision_core.headless_stdio import headless_enabled as _he

    return _he()


def purge_legacy_tag_caches(root: str | Path) -> list[str]:
    """
    Remove repo-map cache dirs from older package names / cache versions.

    Pickled entries may reference the pre-rename ``aider`` module and raise
    ``ModuleNotFoundError`` when loaded under ``bright_vision_core``.
    """
    root = Path(root)
    removed: list[str] = []
    if not root.is_dir():
        return removed
    for path in sorted(root.iterdir()):
        if not path.is_dir():
            continue
        m = LEGACY_TAG_CACHE_PATTERN.match(path.name)
        if not m:
            continue
        if path.name == REPO_MAP_CACHE_DIRNAME:
            continue
        try:
            shutil.rmtree(path)
            removed.append(str(path))
        except OSError:
            pass
    return removed


def safe_cache_len(cache: Any) -> int:
    """``len(diskcache.Cache)`` can unpickle entries; treat failures as empty."""
    try:
        return len(cache)
    except CACHE_LOAD_ERRORS:
        return -1


def configure_vision_runtime(*, force: bool = False) -> None:
    """
    One-time setup for Aider Vision desktop / API child processes.

    - Redirect stdio (headless)
    - Disable tqdm terminal bars
    - Patch tqdm → GUI progress when still invoked from legacy call sites
    """
    global _runtime_configured, _tqdm_patched
    if _runtime_configured and not force:
        return
    _runtime_configured = True

    if not headless_enabled():
        return

    os.environ.setdefault("TQDM_DISABLE", "1")

    from bright_vision_core.headless_stdio import install_headless_stdio

    install_headless_stdio()
    _patch_tqdm_for_headless()


def _patch_tqdm_for_headless() -> None:
    global _tqdm_patched
    if _tqdm_patched:
        return
    try:
        import tqdm as tqdm_mod
    except ImportError:
        return

    _orig = tqdm_mod.tqdm

    def _vision_tqdm(iterable=None, *args, **kwargs):
        if iterable is None:
            return _orig(*args, **kwargs)
        from bright_vision_core.gui_progress import progress_iter

        desc = kwargs.get("desc")
        if desc is None and args and isinstance(args[0], str):
            desc = args[0]
        return progress_iter(
            iterable,
            desc=str(desc or "Working"),
            io=kwargs.get("io"),
            total=kwargs.get("total"),
        )

    tqdm_mod.tqdm = _vision_tqdm
    _tqdm_patched = True
