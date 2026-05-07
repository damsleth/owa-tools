"""Token acquisition.

owa-cal does not own any auth credentials. It shells out to the
`owa-piggy` CLI (must live in $PATH) and consumes its `--json` token
output. owa-piggy owns the token lifecycle in its own profile store;
owa-cal stores nothing more than an optional `owa_piggy_profile`
alias to forward through as `--profile <alias>`.

If we ever need a different identity provider, that lives in
owa-piggy too: every owa-* CLI in the suite is a thin consumer of the
same token contract. This file deliberately knows about owa-piggy and
nothing else.

The token is requested on the Outlook REST audience
(`outlook.office.com`). Microsoft Graph is not a drop-in replacement
for the OWA SPA client owa-piggy borrows: that client does NOT carry
`Calendars.ReadWrite` on the Graph audience - OWA itself calls
Outlook REST for calendar. Switching `api_base` to
`https://graph.microsoft.com/v1.0` without arranging a different
client (which would belong in owa-piggy, not here) returns 403.
"""
import json
import shutil
import subprocess
import sys

from .jwt import token_minutes_remaining


def _owa_piggy_available():
    return shutil.which('owa-piggy') is not None


# owa-cal and owa-piggy version independently. The bridge is a stdout
# JSON contract, not a Python import. We sanity-check the floor once
# per process so a stale owa-piggy fails fast with a clear message
# instead of a confusing JSON-shape error later.
MIN_OWA_PIGGY_VERSION = (0, 6, 0)
_owa_piggy_version_checked = False


def _parse_version(s):
    parts = s.strip().split('.')
    out = []
    for p in parts[:3]:
        try:
            out.append(int(p.split('-', 1)[0]))
        except ValueError:
            return None
    return tuple(out) if len(out) == 3 else None


def _check_owa_piggy_version():
    """Verify owa-piggy on PATH is >= MIN_OWA_PIGGY_VERSION.

    Runs `owa-piggy --version` once per process. Returns True if the
    version is acceptable or unparseable (don't fail closed on a parse
    quirk - the JSON-contract check downstream will still catch real
    breakage). Returns False only when the version is parseable AND
    older than the floor.
    """
    global _owa_piggy_version_checked
    if _owa_piggy_version_checked:
        return True
    _owa_piggy_version_checked = True
    try:
        proc = subprocess.run(
            ['owa-piggy', '--version'],
            capture_output=True, text=True, check=False, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return True
    if proc.returncode != 0:
        return True
    # argparse prints "owa-piggy X.Y.Z" to stdout (or stderr on py<3.10)
    raw = (proc.stdout or proc.stderr).strip().split()
    found = next((_parse_version(t) for t in raw if _parse_version(t)), None)
    if found is None:
        return True
    if found < MIN_OWA_PIGGY_VERSION:
        floor = '.'.join(str(n) for n in MIN_OWA_PIGGY_VERSION)
        have = '.'.join(str(n) for n in found)
        print(
            f'ERROR: owa-piggy {have} is too old; owa-cal needs >= {floor}. '
            f'Upgrade with: brew upgrade damsleth/tap/owa-piggy',
            file=sys.stderr,
        )
        return False
    return True


def _log_token_remaining(access, debug):
    """Debug-only: report the access token's remaining lifetime to stderr."""
    if not debug:
        return
    remaining = token_minutes_remaining(access)
    if remaining is not None:
        print(f'DEBUG: token exchange ok ({remaining}min remaining)', file=sys.stderr)


def _refresh_via_owa_piggy(config, debug=False):
    """Shell out to `owa-piggy token --audience outlook --json [--profile <alias>]`.

    We deliberately do not import owa-piggy; treating it as a sibling
    POSIX util keeps the coupling loose and lets either tool be swapped
    independently. owa-piggy owns the token lifecycle - no refresh
    token flows through owa-cal.
    """
    if not _owa_piggy_available():
        print(
            'ERROR: owa-piggy not found in $PATH. Install with: '
            'brew install damsleth/tap/owa-piggy',
            file=sys.stderr,
        )
        return None
    if not _check_owa_piggy_version():
        return None
    # --audience outlook: owa-cal talks to outlook.office.com, which
    # wants an Outlook-audience token. owa-piggy's default is Graph; a
    # Graph token gets 403 from the Outlook REST endpoint AND lacks
    # Calendars.ReadWrite on Graph itself (see module docstring), so we
    # must pin the audience explicitly.
    argv = ['owa-piggy', 'token', '--audience', 'outlook', '--json']
    profile = (config.get('owa_piggy_profile') or '').strip()
    if profile:
        argv += ['--profile', profile]
    if debug:
        print(f'DEBUG: auth via owa-piggy ({" ".join(argv)})', file=sys.stderr)
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            check=False,
        )
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
    _log_token_remaining(access, debug)
    return access


def do_token_refresh(config, debug=False):
    """Exchange credentials for a new access token via owa-piggy.

    Returns the access token on success, None on failure.
    """
    return _refresh_via_owa_piggy(config, debug=debug)


def setup_auth(config, debug=False):
    """Ensure we have a valid access token, or die.

    Returns (access_token, api_base). Exits the process on failure -
    interactive CLI, so a clear error message is the right thing.
    """
    access = do_token_refresh(config, debug=debug)
    if not access:
        profile = (config.get('owa_piggy_profile') or '').strip()
        hint = f' --profile {profile}' if profile else ''
        suffix = (
            f' or adjust the profile with `owa-cal config --profile <alias>`.'
            if profile else '.'
        )
        print(
            f'ERROR: token refresh failed. Re-seed via '
            f'`owa-piggy setup{hint}`{suffix}',
            file=sys.stderr,
        )
        sys.exit(1)
    return access, 'https://outlook.office.com/api/v2.0'
