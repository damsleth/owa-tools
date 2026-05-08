"""Subprocess-level helpers for the owa-piggy token bridge.

Each consumer CLI's `auth.py` owns its own version-cache state, its
own `_check_owa_piggy_version` (so tests can reset the per-tool global
they were originally written against), and the tool-specific
constants (TOOL_NAME, AUDIENCE, API_BASE). This module owns the
shared mechanics: parsing the version string, running the actual
subprocess, parsing the JSON envelope, and the standard
"couldn't get a token" exit message.

Stdlib only. No third-party deps.
"""
import json
import subprocess
import sys

from .jwt import token_minutes_remaining

MIN_OWA_PIGGY_VERSION = (0, 6, 0)


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


def check_owa_piggy_version(tool_name):
    """Run `owa-piggy --version` once and decide if the floor is met.

    Returns True if the version is acceptable or unparseable (don't
    fail closed on a parse quirk - the JSON-contract check downstream
    will still catch real breakage). Returns False only when the
    version is parseable AND older than the floor.

    The caller (each per-tool auth.py) owns the once-per-process
    cache and is responsible for skipping the call after the first
    invocation.
    """
    try:
        proc = subprocess.run(
            ['owa-piggy', '--version'],
            capture_output=True, text=True, check=False, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return True
    if proc.returncode != 0:
        return True
    raw = (proc.stdout or proc.stderr).strip().split()
    found = next((parse_version(t) for t in raw if parse_version(t)), None)
    if found is None:
        return True
    if found < MIN_OWA_PIGGY_VERSION:
        floor = '.'.join(str(n) for n in MIN_OWA_PIGGY_VERSION)
        have = '.'.join(str(n) for n in found)
        print(
            f'ERROR: owa-piggy {have} is too old; {tool_name} needs >= {floor}. '
            f'Upgrade with: brew upgrade damsleth/tap/owa-piggy',
            file=sys.stderr,
        )
        return False
    return True


def log_token_remaining(access, debug):
    """Debug-only: report the access token's remaining lifetime to stderr."""
    if not debug:
        return
    remaining = token_minutes_remaining(access)
    if remaining is not None:
        print(f'DEBUG: token exchange ok ({remaining}min remaining)', file=sys.stderr)


def run_piggy_token(config, audience, debug=False):
    """Shell out to `owa-piggy token --audience <X> --json [--profile <alias>]`.

    Returns access token string on success, None on failure (errors
    logged to stderr, no exceptions raised). Caller is responsible for
    confirming owa-piggy is on PATH and the version is acceptable
    before calling.
    """
    argv = ['owa-piggy', 'token', '--audience', audience, '--json']
    profile = (config.get('owa_piggy_profile') or '').strip()
    if profile:
        argv += ['--profile', profile]
    if debug:
        print(f'DEBUG: auth via owa-piggy ({" ".join(argv)})', file=sys.stderr)
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, check=False)
    except OSError as e:
        print(f'ERROR: failed to run owa-piggy: {e}', file=sys.stderr)
        return None
    if proc.returncode != 0:
        stderr = proc.stderr.strip()
        if stderr:
            print(stderr, file=sys.stderr)
        return None
    try:
        result = json.loads(proc.stdout)
    except json.JSONDecodeError:
        print('ERROR: owa-piggy returned non-JSON output', file=sys.stderr)
        return None
    access = result.get('access_token')
    if not access:
        return None
    log_token_remaining(access, debug)
    return access


def setup_or_exit(access, config, tool_name, api_base):
    """Translate (access, config, tool_name, api_base) into either
    (access, api_base) or sys.exit(1) with a profile-aware error
    message. Centralizes the message every consumer was duplicating.
    """
    if access:
        return access, api_base
    profile = (config.get('owa_piggy_profile') or '').strip()
    hint = f' --profile {profile}' if profile else ''
    suffix = (
        f' or adjust the profile with `{tool_name} config --profile <alias>`.'
        if profile else '.'
    )
    print(
        f'ERROR: token refresh failed. Re-seed via '
        f'`owa-piggy setup{hint}`{suffix}',
        file=sys.stderr,
    )
    sys.exit(1)
