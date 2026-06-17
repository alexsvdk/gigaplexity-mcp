"""JWT helpers (decode without verification)."""

from __future__ import annotations

import json
import time
from base64 import b64decode

# `_sm_sess` is a signed JWT issued by Keymaster. We only need the payload
# to read `exp` for preflight checks — no cryptographic verification is
# performed (and none is needed for a short-lived session cookie).


def decode_jwt_payload(token: str | None) -> dict:
    """Decode JWT payload without verification.

    Returns an empty dict if the token is missing, malformed, or not a JWT.
    """
    if not token or not isinstance(token, str):
        return {}
    parts = token.split(".")
    if len(parts) != 3:
        return {}
    payload = parts[1]
    # Fix base64 padding
    payload += "=" * (-len(payload) % 4)
    try:
        return json.loads(b64decode(payload))
    except Exception:
        return {}


def jwt_exp(token: str | None) -> int | None:
    """Return JWT `exp` claim as a UNIX timestamp, or None if missing/invalid."""
    payload = decode_jwt_payload(token)
    exp = payload.get("exp")
    try:
        return int(exp) if exp is not None else None
    except (TypeError, ValueError):
        return None


def is_jwt_expired(token: str | None, *, skew_seconds: int = 0) -> bool:
    """Return True if the JWT is expired (or expires within `skew_seconds`).

    Returns True for missing/invalid tokens — they cannot be trusted to be alive.
    """
    exp = jwt_exp(token)
    if exp is None:
        return True
    return exp <= int(time.time()) + max(0, int(skew_seconds))
