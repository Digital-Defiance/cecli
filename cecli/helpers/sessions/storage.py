"""Reading and writing session payloads and reference documents."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional

from cecli.decoding import safe_open
from cecli.helpers import crypto as session_crypto

from .layout import PRIMARY_PAYLOAD_NAME, SESSION_REFERENCE_TYPE, sub_agent_payloads


def encrypt_settings(coder) -> tuple[bool, bytes | None]:
    """Return whether session encryption is on and the resolved key."""
    args = getattr(coder, "args", None)
    if not args or not getattr(args, "session_encrypt", False):
        return False, None

    key_file = getattr(args, "session_key_file", None)

    return True, session_crypto.resolve_key(key_file=key_file)


def resolve_payload_file(coder, io, session_file: Path, quiet: bool = False) -> Path | None:
    """Resolve a session locator to the file holding its payload.

    A locator may be a folder bundle (``{name}/``), a single payload file, or a
    reference document pointing at an auto-save payload in a coder's agent
    folder. Returns ``None`` when the payload cannot be located.
    """
    if session_file.is_dir():
        payload = session_file / PRIMARY_PAYLOAD_NAME
        if payload.is_file():
            return payload

        if not quiet:
            io.tool_error(f"Session folder is missing {PRIMARY_PAYLOAD_NAME}: {session_file}")

        return None

    try:
        raw = session_file.read_bytes()

    except OSError as e:
        if not quiet:
            io.tool_error(f"Error reading session: {e}")

        return None

    if session_crypto.is_encrypted_payload(raw):
        return session_file

    try:
        parsed = json.loads(raw.decode("utf-8"))

    except (UnicodeDecodeError, json.JSONDecodeError):
        return session_file

    if not isinstance(parsed, dict) or parsed.get("type") != SESSION_REFERENCE_TYPE:
        return session_file

    reference = parsed.get("path")
    if not reference:
        if not quiet:
            io.tool_error("Session reference is missing a path.")

        return None

    target = Path(reference)
    if not target.is_absolute():
        target = Path(coder.abs_root_path(reference))

    if not target.exists():
        if not quiet:
            io.tool_error(f"Referenced session file not found: {reference}")

        return None

    return target


def read_payload(coder, io, data_file: Path, quiet: bool = False) -> dict | None:
    """Read a session payload file, decrypting it when necessary."""
    try:
        data = data_file.read_bytes()

    except OSError as e:
        if not quiet:
            io.tool_error(f"Error reading session: {e}")

        return None

    try:
        if session_crypto.is_encrypted_payload(data):
            args = getattr(coder, "args", None)
            key_file = getattr(args, "session_key_file", None) if args else None
            key = session_crypto.resolve_key(key_file=key_file)
            if not key:
                if not quiet:
                    io.tool_error(
                        "Session is encrypted but no key is configured "
                        f"({session_crypto.KEY_ENV} or --session-key-file)."
                    )

                return None

            return session_crypto.decrypt_session_bytes(data, key)

        parsed = json.loads(data.decode("utf-8"))
        if not isinstance(parsed, dict):
            if not quiet:
                io.tool_error("Invalid session format.")

            return None

        return parsed

    except session_crypto.SessionCryptoError as e:
        if not quiet:
            io.tool_error(str(e))

        return None

    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        if not quiet:
            io.tool_error(f"Error loading session: {e}")

        return None


def write_payload(coder, io, data_file: Path, session_data: dict) -> bool:
    """Write a session payload, encrypting it when configured."""
    encrypt_enabled, key = encrypt_settings(coder)

    try:
        data_file.parent.mkdir(parents=True, exist_ok=True)

        if encrypt_enabled:
            if not key:
                io.tool_error(
                    "Session encryption is enabled but no key is configured "
                    f"({session_crypto.KEY_ENV} or --session-key-file)."
                )

                return False

            data_file.write_bytes(session_crypto.encrypt_session_dict(session_data, key))
        else:
            with safe_open(data_file, "w") as f:
                json.dump(session_data, f, indent=2)

        return True

    except session_crypto.SessionCryptoError as e:
        io.tool_error(str(e))

        return False

    except OSError as e:
        io.tool_error(f"Error saving session: {e}")

        return False


def write_reference(coder, io, reference_file: Path, session_name: str, data_file: Path) -> bool:
    """Write a sessions-directory pointer to a payload stored elsewhere."""
    reference = {
        "version": 1,
        "type": SESSION_REFERENCE_TYPE,
        "session_name": session_name,
        "path": _relative_to_root(coder, data_file),
    }

    try:
        reference_file.parent.mkdir(parents=True, exist_ok=True)
        with safe_open(reference_file, "w") as f:
            json.dump(reference, f, indent=2)

        return True

    except OSError as e:
        io.tool_error(f"Error saving session reference: {e}")

        return False


def describe_session(coder, io, name: str, locator: Path) -> Optional[Dict]:
    """Build a list-row description for a saved session locator."""
    data_file = resolve_payload_file(coder, io, locator, quiet=True)
    if data_file is None:
        return None

    raw = data_file.read_bytes()
    encrypted = session_crypto.is_encrypted_payload(raw)

    if encrypted:
        _, key = encrypt_settings(coder)
        if not key:
            return {
                "name": name,
                "file": locator,
                "model": "encrypted",
                "edit_format": "—",
                "num_messages": 0,
                "num_files": 0,
                "num_sub_agents": 0,
                "encrypted": True,
            }

        session_data = session_crypto.decrypt_session_bytes(raw, key)
    else:
        session_data = json.loads(raw.decode("utf-8"))
        if not isinstance(session_data, dict):
            raise ValueError("not a session object")

    chat_history = session_data.get("chat_history", {})
    files = session_data.get("files", {})

    return {
        "name": name,
        "file": locator,
        "model": session_data.get("model", "unknown"),
        "edit_format": session_data.get("edit_format", "unknown"),
        "num_messages": (
            len(chat_history.get("done_messages", [])) + len(chat_history.get("cur_messages", []))
        ),
        "num_files": (
            len(files.get("editable", []))
            + len(files.get("read_only", []))
            + len(files.get("read_only_stubs", []))
        ),
        "num_sub_agents": len(sub_agent_payloads(data_file)),
        "encrypted": encrypted,
    }


def _relative_to_root(coder, data_file: Path) -> str:
    """Store payload paths relative to the coder root when possible."""
    try:
        return str(data_file.relative_to(coder.abs_root_path("")))

    except ValueError:
        return str(data_file)
