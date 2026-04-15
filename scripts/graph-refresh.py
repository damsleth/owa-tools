#!/usr/bin/env python3
"""
Token refresh via Microsoft OAuth2 refresh_token grant.

Uses the opaque refresh token from MSAL/OWA cache to get a new access token
directly from login.microsoftonline.com — no browser required.

Reads from environment variables:
  OUTLOOK_REFRESH_TOKEN   The MSAL RefreshToken.secret value
  OUTLOOK_CLIENT_ID       App client ID (default: OWA's public client)
  OUTLOOK_TENANT_ID       Azure AD tenant ID

Outputs JSON to stdout:
  {"access_token": "eyJ...", "refresh_token": "1.AQ...", "expires_in": 3600}

Errors go to stderr, exit code 1 on failure.
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

# OWA's public client ID (no client_secret required)
DEFAULT_CLIENT_ID = '9199bf20-a13f-4107-85dc-02114787ef48'

# Scope for outlook.office.com (matches the existing JWT audience)
SCOPE = 'https://outlook.office.com/Calendars.ReadWrite openid profile offline_access'


def main():
    refresh_token = os.environ.get('OUTLOOK_REFRESH_TOKEN', '').strip()
    client_id = os.environ.get('OUTLOOK_CLIENT_ID', DEFAULT_CLIENT_ID).strip()
    tenant_id = os.environ.get('OUTLOOK_TENANT_ID', '').strip()

    if not refresh_token:
        print('ERROR: OUTLOOK_REFRESH_TOKEN not set', file=sys.stderr)
        return 1

    if not tenant_id:
        print('ERROR: OUTLOOK_TENANT_ID not set', file=sys.stderr)
        return 1

    url = f'https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token'

    data = urllib.parse.urlencode({
        'grant_type': 'refresh_token',
        'client_id': client_id,
        'refresh_token': refresh_token,
        'scope': SCOPE,
    }).encode('utf-8')

    # SPA refresh tokens (AADSTS9002327) require the Origin header to satisfy
    # the "cross-origin" check that Microsoft enforces for SPA-type clients.
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            'Content-Type': 'application/x-www-form-urlencoded',
            'Origin': 'https://outlook.cloud.microsoft',
        },
        method='POST',
    )

    try:
        with urllib.request.urlopen(req) as resp:
            body = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        err_body = e.read().decode('utf-8', errors='replace')
        try:
            err = json.loads(err_body)
            print(f'ERROR: {err.get("error")}: {err.get("error_description", "")}', file=sys.stderr)
        except Exception:
            print(f'ERROR: HTTP {e.code}: {err_body[:200]}', file=sys.stderr)
        return 1
    except Exception as e:
        print(f'ERROR: {e}', file=sys.stderr)
        return 1

    access_token = body.get('access_token')
    new_refresh_token = body.get('refresh_token')
    expires_in = body.get('expires_in', 0)

    if not access_token:
        print(f'ERROR: No access_token in response: {list(body.keys())}', file=sys.stderr)
        return 1

    print(json.dumps({
        'access_token': access_token,
        'refresh_token': new_refresh_token,
        'expires_in': expires_in,
    }))
    return 0


if __name__ == '__main__':
    sys.exit(main())
