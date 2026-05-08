"""Subprocess-level helpers for the owa-piggy token bridge.

Each consumer CLI's `auth.py` owns only its tool-specific constants
(TOOL_NAME, AUDIENCE, API_BASE). This module owns the shared mechanics:
locating owa-piggy, validating the JSON broker contract, running the
actual subprocess, and parsing the sanitized token envelope.

Stdlib only. No third-party deps.
"""
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass

from .errors import AuthExpiredError, InternalError
from .jwt import token_minutes_remaining
from .secrets import redact

MIN_JSON_BROKER_VERSION = (0, 7, 1)


@dataclass(frozen=True)
class BrokerToken:
    """Sanitized token response from owa-piggy.

    `raw` intentionally excludes refresh_token if an older broker prints one.
    Consumer tools must never persist or log the broker's full token payload.
    """

    access_token: str
    audience: str
    profile: str | None = None
    token_type: str | None = None
    expires_in: int | None = None
    expires_at: int | None = None
    scope: str | None = None
    raw: dict | None = None


def parse_version(s):
    """Tolerant `X.Y.Z[-prerelease]` -> tuple(int, int, int) or None."""
    parts = s.strip().split('.')
    out = []
    for p in parts[:3]:
        try:
            out.append(int(p.split('-', 1)[0]))
        except ValueError:
            return None
    return tuple(out) if len(out) == 3 else None


def _parse_broker_version(text):
    raw = (text or '').strip().split()
    return next((parsed for token in raw if (parsed := parse_version(token))), None)


def _format_version(version):
    return '.'.join(str(n) for n in version)


def _ensure_broker_available(tool_name, min_version):
    if shutil.which('owa-piggy') is None:
        raise AuthExpiredError(
            'owa-piggy not found in $PATH',
            remediation='Install with: brew install damsleth/tap/owa-piggy',
        )
    try:
        proc = subprocess.run(
            ['owa-piggy', '--version'],
            capture_output=True, text=True, check=False, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AuthExpiredError('failed to run owa-piggy --version', cause=exc)
    if proc.returncode != 0:
        raise AuthExpiredError('owa-piggy --version failed')
    found = _parse_broker_version(proc.stdout or proc.stderr)
    if found is None:
        return
    if found < min_version:
        raise AuthExpiredError(
            f'owa-piggy {_format_version(found)} is too old; '
            f'{tool_name} needs >= {_format_version(min_version)}',
            remediation='Upgrade with: brew upgrade damsleth/tap/owa-piggy',
        )


def _optional_int(value):
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _sanitize_token_payload(payload):
    return {key: value for key, value in payload.items() if key != 'refresh_token'}


def get_token(
    *,
    tool_name,
    audience,
    profile=None,
    scope=None,
    min_version=MIN_JSON_BROKER_VERSION,
    debug=False,
):
    """Return a sanitized broker token or raise a typed OwaError.

    This is the new contract used by migrated tools. It validates the
    owa-piggy JSON broker surface and maps expected failure modes to the
    shared exit-code taxonomy.
    """
    _ensure_broker_available(tool_name, min_version)
    argv = ['owa-piggy', 'token', '--audience', audience, '--json']
    if scope:
        argv += ['--scope', scope]
    if profile:
        argv += ['--profile', profile]
    if debug:
        print(f'DEBUG: auth via owa-piggy ({" ".join(argv)})', file=sys.stderr)
    try:
        proc = subprocess.run(
            argv, capture_output=True, text=True, check=False, timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AuthExpiredError('failed to run owa-piggy token', cause=exc)
    if proc.returncode != 0:
        message = redact((proc.stderr or '').strip()) or 'token refresh failed'
        raise AuthExpiredError(message)
    try:
        result = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise InternalError('owa-piggy returned non-JSON output', cause=exc)
    if not isinstance(result, dict):
        raise InternalError('owa-piggy returned an invalid token payload')
    access = result.get('access_token')
    if not isinstance(access, str) or not access:
        raise InternalError('owa-piggy token payload did not include access_token')
    log_token_remaining(access, debug)
    return BrokerToken(
        access_token=access,
        audience=audience,
        profile=profile,
        token_type=result.get('token_type') if isinstance(result.get('token_type'), str) else None,
        expires_in=_optional_int(result.get('expires_in')),
        expires_at=_optional_int(result.get('expires_at')),
        scope=result.get('scope') if isinstance(result.get('scope'), str) else None,
        raw=_sanitize_token_payload(result),
    )


def get_token_for_config(config, *, tool_name, audience, scope=None, debug=False):
    profile = (config.get('owa_piggy_profile') or '').strip()
    return get_token(
        tool_name=tool_name,
        audience=audience,
        profile=profile or None,
        scope=scope,
        debug=debug,
    )


def log_token_remaining(access, debug):
    """Debug-only: report the access token's remaining lifetime to stderr."""
    if not debug:
        return
    remaining = token_minutes_remaining(access)
    if remaining is not None:
        print(f'DEBUG: token exchange ok ({remaining}min remaining)', file=sys.stderr)
