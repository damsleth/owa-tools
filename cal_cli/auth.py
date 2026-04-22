"""Token acquisition.

Two paths:

1. **App registration**: OUTLOOK_APP_CLIENT_ID is set. We hit the AAD
   v2 token endpoint directly with refresh_token grant and persist the
   rotated refresh token back to config, since refresh tokens are
   single-use.
2. **owa-piggy bridge**: no app registration. We shell out to the
   `owa-piggy` CLI (which must live in $PATH) and take its --json
   output. cal-cli stores no refresh token on this path; owa-piggy
   owns the token lifecycle in its own profile store. An optional
   `owa_piggy_profile` alias forwards through as `--profile <alias>`.
   Both tools live in the same CLI dir; think of them as two POSIX
   utils piped together.

Both paths request an Outlook-audience token (`outlook.office.com`).
Microsoft Graph is not a drop-in replacement: OWA's first-party SPA
client (which owa-piggy borrows) does NOT carry `Calendars.ReadWrite`
on the Graph audience - OWA itself calls Outlook REST for calendar,
so the Graph-audience consent grant for that client only covers
Teams/Files/Directory. Switching `api_base` to
`https://graph.microsoft.com/v1.0` without also registering your own
app will return 403 on every call.
"""
import json
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

from . import config as config_mod
from .jwt import token_minutes_remaining

OUTLOOK_SCOPE = (
    'https://outlook.office.com/Calendars.ReadWrite '
    'openid profile offline_access'
)


def _owa_piggy_available():
    return shutil.which('owa-piggy') is not None


def refresh_via_app_registration(refresh_token, tenant_id, client_id):
    """Call AAD v2 token endpoint with the app-registration client_id.

    Returns the full response dict or None on failure (errors logged to
    stderr, no exceptions raised).
    """
    url = f'https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token'
    data = urllib.parse.urlencode({
        'grant_type': 'refresh_token',
        'client_id': client_id,
        'refresh_token': refresh_token,
        'scope': OUTLOOK_SCOPE,
    }).encode('utf-8')
    req = urllib.request.Request(
        url,
        data=data,
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        err_body = e.read().decode('utf-8', errors='replace')
        try:
            err = json.loads(err_body)
            code = err.get('error', '')
            desc = err.get('error_description', '').split('\r\n')[0]
            print(f'ERROR: {code}: {desc}', file=sys.stderr)
        except Exception:
            print(f'ERROR: HTTP {e.code}: {err_body[:200]}', file=sys.stderr)
        return None
    except urllib.error.URLError as e:
        print(f'ERROR: {e.reason}', file=sys.stderr)
        return None


def _refresh_via_app_registration(config, debug=False):
    refresh_token = config.get('OUTLOOK_REFRESH_TOKEN', '').strip()
    tenant_id = config.get('OUTLOOK_TENANT_ID', '').strip()
    client_id = config.get('OUTLOOK_APP_CLIENT_ID', '').strip()
    if not refresh_token or not tenant_id:
        return None
    if debug:
        print(f'DEBUG: auth via app registration ({client_id})', file=sys.stderr)
    result = refresh_via_app_registration(refresh_token, tenant_id, client_id)
    if not result:
        return None
    access = result.get('access_token')
    if not access:
        return None
    new_refresh = result.get('refresh_token')
    if new_refresh and new_refresh != refresh_token:
        config['OUTLOOK_REFRESH_TOKEN'] = new_refresh
        try:
            config_mod.config_set('OUTLOOK_REFRESH_TOKEN', new_refresh)
        except Exception as e:
            print(f'WARN: failed to persist rotated refresh token: {e}', file=sys.stderr)
    if debug:
        remaining = token_minutes_remaining(access)
        if remaining is not None:
            print(f'DEBUG: token exchange ok ({remaining}min remaining)', file=sys.stderr)
    return access


def _refresh_via_owa_piggy(config, debug=False):
    """Shell out to `owa-piggy token --audience outlook --json [--profile <alias>]`.

    We deliberately do not import owa-piggy; treating it as a sibling
    POSIX util keeps the coupling loose and lets either tool be swapped
    independently. owa-piggy owns the token lifecycle - no refresh
    token flows through cal-cli on this path.
    """
    if not _owa_piggy_available():
        print(
            'ERROR: owa-piggy not found in $PATH. Install with: '
            'brew install damsleth/tap/owa-piggy',
            file=sys.stderr,
        )
        return None
    # --audience outlook: cal-cli talks to outlook.office.com, which
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
    if debug:
        remaining = token_minutes_remaining(access)
        if remaining is not None:
            print(f'DEBUG: token exchange ok ({remaining}min remaining)', file=sys.stderr)
    return access


def do_token_refresh(config, debug=False):
    """Exchange credentials for a new access token.

    Uses the app-registration path if OUTLOOK_APP_CLIENT_ID is set,
    otherwise shells out to owa-piggy. Returns the access token on
    success, None on failure.
    """
    if config.get('OUTLOOK_APP_CLIENT_ID'):
        return _refresh_via_app_registration(config, debug=debug)
    return _refresh_via_owa_piggy(config, debug=debug)


def setup_auth(config, debug=False):
    """Ensure we have a valid access token, or die.

    Returns (access_token, api_base). Exits the process on missing
    config or refresh failure - interactive CLI, so a clear error
    message is the right thing.
    """
    if config.get('OUTLOOK_APP_CLIENT_ID'):
        if not config.get('OUTLOOK_REFRESH_TOKEN') or not config.get('OUTLOOK_TENANT_ID'):
            print(
                'ERROR: app-registration path needs OUTLOOK_REFRESH_TOKEN '
                'and OUTLOOK_TENANT_ID in ~/.config/cal-cli/config.',
                file=sys.stderr,
            )
            sys.exit(1)
    access = do_token_refresh(config, debug=debug)
    if not access:
        if config.get('OUTLOOK_APP_CLIENT_ID'):
            print(
                'ERROR: token refresh failed. Run `cal-cli config` to '
                'inspect settings.',
                file=sys.stderr,
            )
        else:
            profile = (config.get('owa_piggy_profile') or '').strip()
            hint = f' --profile {profile}' if profile else ''
            print(
                f'ERROR: token refresh failed. Re-seed via '
                f'`owa-piggy setup{hint}`'
                + (f' or adjust the profile with `cal-cli config --profile <alias>`.' if profile else '.'),
                file=sys.stderr,
            )
        sys.exit(1)
    return access, 'https://outlook.office.com/api/v2.0'
