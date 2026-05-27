"""Optional AES-256-GCM encryption for on-disk cecli session files."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any

MAGIC = b"CECLI_ENCRYPTED_SESSION_v1\n"
KEY_ENV = "CECLI_SESSION_KEY"
KEY_BYTES = 32


class SessionCryptoError(Exception):
    """Session encrypt/decrypt failed."""


def is_encrypted_payload(data: bytes) -> bool:
    return data.startswith(MAGIC)


def resolve_key(*, key_file: str | Path | None = None) -> bytes | None:
    """Load a 32-byte key from CECLI_SESSION_KEY (urlsafe base64) or a key file."""
    raw = os.environ.get(KEY_ENV, "").strip()
    if raw:
        key = _decode_key_b64(raw)
        if key is not None:
            return key
    if key_file:
        path = Path(key_file).expanduser()
        if path.is_file():
            text = path.read_text(encoding="utf-8").strip()
            key = _decode_key_b64(text)
            if key is not None:
                return key
    return None


def _decode_key_b64(text: str) -> bytes | None:
    try:
        padded = text + "=" * (-len(text) % 4)
        key = base64.urlsafe_b64decode(padded.encode("ascii"))
    except (ValueError, UnicodeEncodeError):
        return None
    if len(key) != KEY_BYTES:
        return None
    return key


def encrypt_session_dict(session_data: dict[str, Any], key: bytes) -> bytes:
    if len(key) != KEY_BYTES:
        raise SessionCryptoError(f"Session key must be {KEY_BYTES} bytes.")
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as err:
        raise SessionCryptoError(
            "Session encryption requires the cryptography package (pip install cryptography)."
        ) from err

    plaintext = json.dumps(session_data, ensure_ascii=False).encode("utf-8")
    nonce = os.urandom(12)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, None)
    payload = base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")
    return MAGIC + payload.encode("ascii") + b"\n"


def decrypt_session_bytes(data: bytes, key: bytes) -> dict[str, Any]:
    if len(key) != KEY_BYTES:
        raise SessionCryptoError(f"Session key must be {KEY_BYTES} bytes.")
    if not is_encrypted_payload(data):
        try:
            parsed = json.loads(data.decode("utf-8"))
        except json.JSONDecodeError as err:
            raise SessionCryptoError("Invalid session file (not JSON).") from err
        if not isinstance(parsed, dict):
            raise SessionCryptoError("Invalid session format.")
        return parsed

    body = data[len(MAGIC) :].strip()
    if not body:
        raise SessionCryptoError("Encrypted session file is empty.")
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as err:
        raise SessionCryptoError(
            "Session encryption requires the cryptography package (pip install cryptography)."
        ) from err

    try:
        blob = base64.urlsafe_b64decode(body + b"=" * (-len(body) % 4))
    except ValueError as err:
        raise SessionCryptoError("Encrypted session payload is invalid.") from err
    if len(blob) < 13:
        raise SessionCryptoError("Encrypted session payload is too short.")
    nonce, ciphertext = blob[:12], blob[12:]
    try:
        plaintext = AESGCM(key).decrypt(nonce, ciphertext, None)
    except Exception as err:
        raise SessionCryptoError("Could not decrypt session (wrong key or corrupted file).") from err
    try:
        parsed = json.loads(plaintext.decode("utf-8"))
    except json.JSONDecodeError as err:
        raise SessionCryptoError("Decrypted session is not valid JSON.") from err
    if not isinstance(parsed, dict):
        raise SessionCryptoError("Invalid session format.")
    return parsed
