"""
Local API authentication for aider-vision.

Policy
------
- ``AIDER_VISION_TOKEN`` set → Bearer token required on all routes except ``/health``.
- Listening on loopback only (``127.0.0.1`` / ``::1`` / ``localhost``) and no token → auth
  disabled (convenient local dev).
- Listening on a non-loopback address without a token → startup refused (see
  ``validate_listen_address``).
"""

from __future__ import annotations

import os
import secrets
from ipaddress import ip_address

TOKEN_ENV = "AIDER_VISION_TOKEN"
TOKEN_ENV_ALIASES = ("AIDER_VISION_TOKEN", "BRIGHT_VISION_TOKEN")

_auth_required = False
_expected_token: str | None = None


def get_token_from_env() -> str | None:
    for key in TOKEN_ENV_ALIASES:
        value = os.environ.get(key)
        if value is not None and value.strip() != "":
            return value
    return None


def is_loopback_host(host: str) -> bool:
    if host in ("localhost", "::1"):
        return True
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return False


def validate_listen_address(host: str) -> None:
    """Refuse wide-open listens without a shared secret."""
    if is_loopback_host(host):
        return
    if get_token_from_env():
        return
    raise SystemExit(
        f"Refusing to bind to {host!r} without {TOKEN_ENV}.\n"
        f"Set {TOKEN_ENV} in the environment, or use --host 127.0.0.1 for local-only dev."
    )


def configure_auth(listen_host: str) -> None:
    """Call once before serving (e.g. from ``vision_serve.py``)."""
    global _auth_required, _expected_token
    token = get_token_from_env()
    _expected_token = token
    if token:
        _auth_required = True
    elif is_loopback_host(listen_host):
        _auth_required = False
    else:
        _auth_required = True


def auth_enabled() -> bool:
    return _auth_required


def startup_message(listen_host: str) -> str:
    if _auth_required and _expected_token:
        return f"API auth enabled ({TOKEN_ENV}); send Authorization: Bearer <token>"
    if is_loopback_host(listen_host):
        return (
            f"Local dev: API auth disabled on {listen_host}. "
            f"Set {TOKEN_ENV} to require a Bearer token."
        )
    return "API auth enabled"


def verify_bearer(authorization: str | None) -> bool:
    if not _auth_required:
        return True
    if not _expected_token:
        return False
    if not authorization or not authorization.lower().startswith("bearer "):
        return False
    provided = authorization.split(" ", 1)[1].strip()
    return secrets.compare_digest(provided, _expected_token)


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def reset_auth_for_tests() -> None:
    """Test helper only."""
    global _auth_required, _expected_token
    _auth_required = False
    _expected_token = None
