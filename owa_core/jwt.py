"""JWT segment parser. No signature validation; reads exp/scp claims.

Public surface:
    decode(token: str) -> dict           # header + payload, no verification
    decode_segment(seg: str) -> dict     # one base64url+json segment
    expires_at(token: str) -> int        # unix seconds
    minutes_remaining(token: str) -> int | None  # safe; None on parse fail
    scopes(token: str) -> list[str]      # 'scp' claim split
    scopes_set(token: str) -> set[str]   # union of 'scp' (str) + 'roles' (list)
    audience(token: str) -> str | None   # 'aud' claim or None
"""
from __future__ import annotations

import base64
import json
import time

from .errors import UsageError


def decode_segment(seg: str) -> dict:
    """Base64url-decode a JWT segment and parse it as JSON.

    Public alias for the internal helper; kept stable so per-tool
    `jwt.py` modules can re-export it with the legacy name
    `decode_jwt_segment`.
    """
    pad = "=" * (-len(seg) % 4)
    try:
        raw = base64.urlsafe_b64decode(seg + pad)
        return json.loads(raw)
    except (ValueError, json.JSONDecodeError) as e:
        raise UsageError(f"invalid JWT segment: {e}") from e


# Backwards-compat alias for the original private name.
_decode_segment = decode_segment


def decode(token: str) -> dict:
    """Return {'header': ..., 'payload': ...}. No signature check."""
    parts = token.split(".")
    if len(parts) < 2:
        raise UsageError("invalid JWT: expected at least two segments")
    return {"header": decode_segment(parts[0]), "payload": decode_segment(parts[1])}


def expires_at(token: str) -> int:
    """Unix seconds from the 'exp' claim. Raises UsageError if missing."""
    payload = decode(token)["payload"]
    exp = payload.get("exp")
    if not isinstance(exp, (int, float)):
        raise UsageError("JWT missing or non-numeric 'exp' claim")
    return int(exp)


def minutes_remaining(token: str) -> int | None:
    """Minutes until ``exp``, or None on any parse failure.

    Suite tools historically used this for debug-mode logging; it must
    never raise.
    """
    try:
        return int((expires_at(token) - time.time()) / 60)
    except Exception:
        return None


def scopes(token: str) -> list[str]:
    """Split the 'scp' claim on whitespace. Empty list if absent."""
    payload = decode(token)["payload"]
    scp = payload.get("scp", "")
    if not isinstance(scp, str):
        return []
    return [s for s in scp.split() if s]


def scopes_set(token: str) -> set[str]:
    """Union of 'scp' (delegated, space-separated) and 'roles' (app-only,
    list). Empty set on any parse failure.
    """
    try:
        payload = decode(token)["payload"]
    except UsageError:
        return set()
    out: set[str] = set()
    scp = payload.get("scp")
    if isinstance(scp, str):
        out.update(s for s in scp.split() if s)
    roles = payload.get("roles")
    if isinstance(roles, list):
        out.update(r for r in roles if isinstance(r, str))
    return out


def audience(token: str) -> str | None:
    """Return the 'aud' claim or None on any parse failure."""
    try:
        return decode(token)["payload"].get("aud")
    except UsageError:
        return None
