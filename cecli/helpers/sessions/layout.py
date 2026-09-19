"""On-disk layout for saved sessions.

Two shapes are supported:

* a single ``{name}.json`` file (optionally a reference document pointing at an
  auto-save payload held in a coder's agent folder), and
* a ``{name}/`` folder bundle holding ``primary.json`` plus an ``s/`` tree of
  sub-agent ``agent.json`` payloads.

Sub-agent payloads always live in an ``s/{child}/`` directory beside the primary
payload. That lets the same discovery logic cover auto-save payloads (which use
``s/{uuid}/{session}.json``) and folder bundles (``s/{child}/agent.json``).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Tuple

SESSION_REFERENCE_TYPE = "session-reference"
PRIMARY_PAYLOAD_NAME = "primary.json"
SUB_AGENT_PAYLOAD_NAME = "agent.json"
SUB_AGENT_DIR_NAME = "s"


def session_directory(coder) -> Path:
    """Return (and create) the coder's ``.cecli/sessions`` directory."""
    session_dir = Path(coder.abs_root_path(".cecli/sessions"))
    os.makedirs(session_dir, exist_ok=True)

    return session_dir


def entry_for(session_dir: Path, session_name: str) -> Path:
    """Return the canonical ``sessions/{name}.json`` file path."""
    return session_dir / f"{session_name}.json"


def bundle_dir(session_dir: Path, session_name: str) -> Path:
    """Return the ``sessions/{name}/`` folder bundle path."""
    return session_dir / session_name


def agent_payload_file(coder, session_name: str) -> Path:
    """Return the auto-save payload path inside the coder's agent folder."""
    rel_path = coder.local_agent_folder(f"{session_name}.json")

    return Path(coder.abs_root_path(rel_path))


def sub_agents_dir(primary_payload: Path) -> Path:
    """Return the ``s/`` directory that owns a primary payload's sub-agents."""
    return primary_payload.parent / SUB_AGENT_DIR_NAME


def primary_payload_in(directory: Path) -> Path | None:
    """Return the primary payload inside a folder bundle, if present."""
    candidate = directory / PRIMARY_PAYLOAD_NAME

    return candidate if candidate.is_file() else None


def payload_in_sub_dir(sub_dir: Path, primary_name: str) -> Path | None:
    """Return the payload held by one sub-agent directory.

    Folder bundles name it ``agent.json``; auto-save payloads reuse the primary
    payload's filename.
    """
    candidate = sub_dir / SUB_AGENT_PAYLOAD_NAME
    if candidate.is_file():
        return candidate

    candidate = sub_dir / primary_name
    if candidate.is_file():
        return candidate

    return None


def sub_agent_payloads(primary_payload: Path) -> List[Path]:
    """Return every sub-agent payload stored beside ``primary_payload``."""
    subs_dir = sub_agents_dir(primary_payload)
    if not subs_dir.is_dir():
        return []

    payloads = []
    for sub_dir in sorted(subs_dir.iterdir()):
        if not sub_dir.is_dir():
            continue

        payload = payload_in_sub_dir(sub_dir, primary_payload.name)
        if payload is not None:
            payloads.append(payload)

    return payloads


def discover_entries(session_dir: Path) -> List[Tuple[str, Path]]:
    """Return ``(name, locator)`` for every saved session in ``session_dir``.

    A locator is either a ``{name}.json`` file or a ``{name}/`` folder bundle;
    callers resolve it to the payload file they need.
    """
    entries: Dict[str, Path] = {}
    for path in session_dir.iterdir():
        if path.is_file() and path.suffix == ".json":
            entries[path.stem] = path
        elif path.is_dir() and primary_payload_in(path) is not None:
            entries[path.name] = path

    return sorted(entries.items())
