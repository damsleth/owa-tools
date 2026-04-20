"""Token acquisition.

Two paths:

1. **App registration**: OUTLOOK_APP_CLIENT_ID is set. We hit the AAD
   v2 token endpoint directly with refresh_token grant.
2. **owa-piggy bridge**: no app registration. We shell out to the
   `owa-piggy` CLI (which must live in $PATH) and take its --json
   output. Both tools live in the same CLI dir; think of them as two
   POSIX utils piped together.

On success we persist the rotated refresh token back to config, since
refresh tokens are single-use.
"""
import json
import os
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


def refresh_via_owa_piggy(refresh_token, tenant_id):
    """Shell out to owa-piggy --json with OWA_* env vars set.

    We deliberately do not import owa-piggy; treating it as a sibling
    POSIX util keeps the coupling loose and lets either tool be swapped
    independently.
    """
    if not _owa_piggy_available():
        print(
            'ERROR: owa-piggy not found in $PATH. Install with: '
            'brew install damsleth/tap/owa-piggy',
            file=sys.stderr,
        )
        return None
    env = os.environ.copy()
    if refresh_token:
        env['OWA_REFRESH_TOKEN'] = refresh_token
    if tenant_id:
        env['OWA_TENANT_ID'] = tenant_id
    try:
        # --outlook: cal-cli talks to outlook.office.com, which wants an
        # Outlook-audience token. owa-piggy's default is Graph; a Graph
        # token gets 401 from the Outlook REST endpoint.
        proc = subprocess.run(
            ['owa-piggy', '--outlook', '--json'],
            env=env,
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
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        print('ERROR: owa-piggy returned non-JSON output', file=sys.stderr)
        return None


def do_token_refresh(config, debug=False):
    """Exchange the configured refresh token for a new access token.

    Uses the app-registration path if OUTLOOK_APP_CLIENT_ID is set,
    otherwise shells out to owa-piggy. On success: persists rotated
    refresh token back to config (if rotated), returns the access
    token. On failure: returns None.
    """
    refresh_token = config.get('OUTLOOK_REFRESH_TOKEN', '').strip()
    tenant_id = config.get('OUTLOOK_TENANT_ID', '').strip()
    client_id = config.get('OUTLOOK_APP_CLIENT_ID', '').strip()
    if not refresh_token or not tenant_id:
        return None

    if client_id:
        if debug:
            print(f'DEBUG: auth via app registration ({client_id})', file=sys.stderr)
        result = refresh_via_app_registration(refresh_token, tenant_id, client_id)
    else:
        if debug:
            print('DEBUG: auth via owa-piggy', file=sys.stderr)
        result = refresh_via_owa_piggy(refresh_token, tenant_id)

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


def setup_auth(config, debug=False):
    """Ensure we have a valid access token, or die.

    Returns (access_token, api_base, api_case). Exits the process on
    missing config or refresh failure - interactive CLI, so a clear
    error message is the right thing.
    """
    if not config.get('OUTLOOK_REFRESH_TOKEN') or not config.get('OUTLOOK_TENANT_ID'):
        print(
            'ERROR: no auth configured. Run: '
            'cal-cli config --refresh-token <t> --tenant-id <id>',
            file=sys.stderr,
        )
        sys.exit(1)
    access = do_token_refresh(config, debug=debug)
    if not access:
        print(
            'ERROR: token refresh failed. Run `cal-cli config` to inspect '
            'settings, or re-seed via `owa-piggy --setup`.',
            file=sys.stderr,
        )
        sys.exit(1)
    return access, 'https://outlook.office.com/api/v2.0', 'pascal'
