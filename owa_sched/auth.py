"""Token acquisition. Mirrors owa-people: shell out to owa-piggy on
PATH, audience=graph. The Graph endpoint /me/calendar/getSchedule
needs Calendars.Read.Shared on the Graph audience, which the OWA
SPA scopes do carry.
"""
import json
import shutil
import subprocess
import sys

from owa_core.jwt import token_minutes_remaining


def _owa_piggy_available():
    return shutil.which('owa-piggy') is not None


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
    raw = (proc.stdout or proc.stderr).strip().split()
    found = next((_parse_version(t) for t in raw if _parse_version(t)), None)
    if found is None:
        return True
    if found < MIN_OWA_PIGGY_VERSION:
        floor = '.'.join(str(n) for n in MIN_OWA_PIGGY_VERSION)
        have = '.'.join(str(n) for n in found)
        print(
            f'ERROR: owa-piggy {have} is too old; owa-sched needs >= {floor}. '
            f'Upgrade with: brew upgrade damsleth/tap/owa-piggy',
            file=sys.stderr,
        )
        return False
    return True


def _log_token_remaining(access, debug):
    if not debug:
        return
    remaining = token_minutes_remaining(access)
    if remaining is not None:
        print(f'DEBUG: token exchange ok ({remaining}min remaining)', file=sys.stderr)


def _refresh_via_owa_piggy(config, debug=False):
    if not _owa_piggy_available():
        print(
            'ERROR: owa-piggy not found in $PATH. Install with: '
            'brew install damsleth/tap/owa-piggy',
            file=sys.stderr,
        )
        return None
    if not _check_owa_piggy_version():
        return None
    argv = ['owa-piggy', 'token', '--audience', 'graph', '--json']
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
    _log_token_remaining(access, debug)
    return access


def do_token_refresh(config, debug=False):
    return _refresh_via_owa_piggy(config, debug=debug)


def setup_auth(config, debug=False):
    access = do_token_refresh(config, debug=debug)
    if not access:
        profile = (config.get('owa_piggy_profile') or '').strip()
        hint = f' --profile {profile}' if profile else ''
        suffix = (
            ' or adjust the profile with `owa-sched config --profile <alias>`.'
            if profile else '.'
        )
        print(
            f'ERROR: token refresh failed. Re-seed via '
            f'`owa-piggy setup{hint}`{suffix}',
            file=sys.stderr,
        )
        sys.exit(1)
    return access, 'https://graph.microsoft.com/v1.0'
