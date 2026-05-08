"""Token acquisition.

owa-graph does not own any auth credentials. It shells out to the
`owa-piggy` CLI (must live in $PATH) and consumes its `--json` token
output. owa-piggy owns the token lifecycle in its own profile store;
owa-graph stores nothing more than an optional `owa_piggy_profile`
alias to forward through as `--profile <alias>`.

Audience defaults to Graph (`https://graph.microsoft.com`). Pass
`--audience <name>` to retarget at any other FOCI audience owa-piggy
knows about (Outlook REST, Teams, Azure Mgmt, KeyVault, etc.). The
audience also picks the API base URL so the same CLI can hit different
APIs with the same query ergonomics.

Caveat: the OWA first-party SPA client owa-piggy borrows does NOT
carry full Graph permissions. Graph-audience consent covers
Teams/Files/Directory and similar; calls that need Calendars.ReadWrite,
Mail.ReadWrite, etc. on Graph will 403. Use the audience-specific
endpoints (e.g. `--audience outlook` for mail/calendar) instead.
"""
import json
import shutil
import subprocess
import sys

from owa_core.jwt import token_minutes_remaining

# Audience short name -> API base URL we issue requests against. Mirrors
# owa-piggy/owa_piggy/scopes.py:KNOWN_AUDIENCES, but where that table
# returns the *AAD audience host* (used to compose `<host>/.default`
# scopes), this one returns the *API base* including the version path so
# `owa-graph GET /me --audience outlook` lands on Outlook REST v2.0
# rather than the bare `outlook.office.com` host.
AUDIENCE_API_BASE = {
    'graph':      'https://graph.microsoft.com/v1.0',
    'outlook':    'https://outlook.office.com/api/v2.0',
    'outlook365': 'https://outlook.office365.com/api/v2.0',
    'teams':      'https://api.spaces.skype.com',
    'azure':      'https://management.azure.com',
    'keyvault':   'https://vault.azure.net',
    'storage':    'https://storage.azure.com',
    'sql':        'https://database.windows.net',
    'substrate':  'https://substrate.office.com',
    'manage':     'https://manage.office.com/api/v1.0',
    'powerbi':    'https://api.powerbi.com/v1.0',
    'flow':       'https://service.flow.microsoft.com',
    'devops':     'https://app.vssps.visualstudio.com',
}

GRAPH_BETA_BASE = 'https://graph.microsoft.com/beta'


def _owa_piggy_available():
    return shutil.which('owa-piggy') is not None


# owa-graph and owa-piggy version independently. The bridge is a stdout
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
    raw = (proc.stdout or proc.stderr).strip().split()
    found = next((_parse_version(t) for t in raw if _parse_version(t)), None)
    if found is None:
        return True
    if found < MIN_OWA_PIGGY_VERSION:
        floor = '.'.join(str(n) for n in MIN_OWA_PIGGY_VERSION)
        have = '.'.join(str(n) for n in found)
        print(
            f'ERROR: owa-piggy {have} is too old; owa-graph needs >= {floor}. '
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


def _refresh_via_owa_piggy(config, audience='graph', debug=False):
    """Shell out to `owa-piggy token --audience <name> --json [--profile <alias>]`."""
    if not _owa_piggy_available():
        print(
            'ERROR: owa-piggy not found in $PATH. Install with: '
            'brew install damsleth/tap/owa-piggy',
            file=sys.stderr,
        )
        return None
    if not _check_owa_piggy_version():
        return None
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
    _log_token_remaining(access, debug)
    return access


def resolve_api_base(audience, beta=False):
    """Audience short-name -> API base URL.

    `--beta` only flips Graph's base; it has no effect on other
    audiences. Unknown audiences exit the process - typos here would
    otherwise produce a confusing 401/404 against a hand-built URL.
    """
    if audience == 'graph':
        return GRAPH_BETA_BASE if beta else AUDIENCE_API_BASE['graph']
    base = AUDIENCE_API_BASE.get(audience)
    if not base:
        known = ', '.join(sorted(AUDIENCE_API_BASE))
        print(
            f'ERROR: unknown audience {audience!r}. Known: {known}',
            file=sys.stderr,
        )
        sys.exit(1)
    if beta:
        print(
            f'WARN: --beta has no effect on audience {audience!r}; ignoring',
            file=sys.stderr,
        )
    return base


def do_token_refresh(config, audience='graph', debug=False):
    """Exchange credentials for a new access token via owa-piggy."""
    return _refresh_via_owa_piggy(config, audience=audience, debug=debug)


def setup_auth(config, audience='graph', beta=False, debug=False):
    """Ensure we have a valid access token, or die.

    Returns (access_token, api_base). Exits the process on missing
    config or refresh failure - interactive CLI, so a clear error
    message is the right thing.
    """
    api_base = resolve_api_base(audience, beta=beta)
    access = do_token_refresh(config, audience=audience, debug=debug)
    if not access:
        profile = (config.get('owa_piggy_profile') or '').strip()
        hint = f' --profile {profile}' if profile else ''
        tail = (
            f' or adjust the profile with `owa-graph config --profile <alias>`.'
            if profile else '.'
        )
        print(
            f'ERROR: token refresh failed. Re-seed via '
            f'`owa-piggy setup{hint}`' + tail,
            file=sys.stderr,
        )
        sys.exit(1)
    return access, api_base
