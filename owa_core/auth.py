"""owa-piggy bridge. Subprocess only; no Python import of owa-piggy.

Public surface:
    get_token(profile, audience, scope=None) -> Token
    require_min_piggy(min_version: str) -> None
    verify_identity(token, audience) -> dict

require_min_piggy parses `owa-piggy --version` text output today
(current contract) and prefers structured JSON output when owa-piggy
ships `--version --json` in the future. The text-parse fallback is the
long-term support path; JSON is an additive optimization.

get_token shells out to:
    owa-piggy [--profile <alias>] token --audience <X> [--scope <s>] --json

and parses the resulting envelope. Subprocess failures map into errors
from owa_core.errors.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass

from .errors import AuthExpiredError, InternalError, UsageError
from .jwt import expires_at as _jwt_exp
from .jwt import scopes as _jwt_scopes


@dataclass
class Token:
    access_token: str
    expires_at: int
    scopes: list[str]
    audience: str


_VERSION_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)")


def _parse_semver(s: str) -> tuple[int, int, int] | None:
    m = _VERSION_RE.search(s)
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def _which_piggy() -> str:
    p = shutil.which("owa-piggy")
    if not p:
        raise UsageError(
            "owa-piggy not found in $PATH",
            hint="brew install damsleth/tap/owa-piggy",
        )
    return p


def require_min_piggy(min_version: str) -> None:
    """Raise UsageError if owa-piggy is older than min_version (semver)."""
    floor = _parse_semver(min_version)
    if floor is None:
        raise UsageError(f"invalid version floor: {min_version!r}")
    piggy = _which_piggy()
    try:
        proc = subprocess.run(
            [piggy, "--version"],
            capture_output=True, text=True, check=False, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        raise InternalError(f"failed to invoke owa-piggy: {e}") from e
    if proc.returncode != 0:
        # Don't fail closed on a non-zero exit; the JSON contract check
        # downstream catches real breakage.
        return
    raw = (proc.stdout or proc.stderr).strip()
    found = _parse_semver(raw)
    if found is None:
        return
    if found < floor:
        have = ".".join(str(n) for n in found)
        want = ".".join(str(n) for n in floor)
        raise UsageError(
            f"owa-piggy {have} is too old; need >= {want}",
            hint="brew upgrade damsleth/tap/owa-piggy",
        )


def get_token(
    profile: str | None,
    audience: str,
    scope: str | None = None,
) -> Token:
    """Borrow an access token from owa-piggy. Subprocess + JSON only.

    Maps owa-piggy failure into AuthExpiredError so callers exit with
    code 11 by default; the hint points at re-seeding.
    """
    piggy = _which_piggy()
    argv = [piggy]
    if profile:
        argv += ["--profile", profile]
    argv += ["token", "--audience", audience, "--json"]
    if scope:
        argv += ["--scope", scope]
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, check=False)
    except OSError as e:
        raise InternalError(f"failed to run owa-piggy: {e}") from e
    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout or "owa-piggy failed").strip().splitlines()[-1]
        hint = "re-seed with `owa-piggy setup`"
        if profile:
            hint = f"re-seed with `owa-piggy setup --profile {profile}`"
        raise AuthExpiredError(msg, hint=hint)
    try:
        result = json.loads(proc.stdout)
    except (json.JSONDecodeError, ValueError) as e:
        raise InternalError(f"owa-piggy returned non-JSON output: {e}") from e
    access = result.get("access_token") if isinstance(result, dict) else None
    if not isinstance(access, str) or not access:
        raise AuthExpiredError("owa-piggy returned no access_token")
    try:
        exp = _jwt_exp(access)
    except UsageError:
        exp = 0
    try:
        scopes = _jwt_scopes(access)
    except UsageError:
        scopes = []
    return Token(access_token=access, expires_at=exp, scopes=scopes, audience=audience)


def verify_identity(token: Token, audience: str) -> dict:
    """Decode the token payload and return basic identity claims.

    Does not call any network. The returned dict contains ``aud``,
    ``upn``, ``oid``, ``tid``, and ``scopes`` when present.
    """
    from .jwt import decode as _decode
    payload = _decode(token.access_token).get("payload", {})
    return {
        "aud": payload.get("aud"),
        "upn": payload.get("upn") or payload.get("preferred_username"),
        "oid": payload.get("oid"),
        "tid": payload.get("tid"),
        "scopes": token.scopes,
        "audience_requested": audience,
        "expires_at": token.expires_at,
    }
