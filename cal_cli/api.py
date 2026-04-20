"""Outlook REST / Graph HTTP helper.

One function: api_request. Returns parsed JSON or None (for
return-to-caller failures). For auth/permission failures we exit the
process with a clear message - cal-cli is a CLI, not a library, and
there is no recovery path for a 401 except telling the user to re-run.
"""
import json
import sys
import urllib.error
import urllib.parse
import urllib.request


def api_request(method, base, endpoint, access_token, body=None, debug=False):
    """Issue a request against Outlook REST / Graph.

    - `base` and `endpoint` are joined with a single slash.
    - `body` is dict-serialised to JSON when non-None.
    - Returns parsed JSON on 2xx, None on 404/429 (caller decides),
      and exits on 401/403 (unrecoverable without reconfig).
    """
    url = f'{base}/{endpoint}'
    if debug:
        print(f'DEBUG: {method} {url}', file=sys.stderr)
        if body is not None:
            print(f'DEBUG: body: {json.dumps(body)[:500]}', file=sys.stderr)

    data = None
    headers = {'Authorization': f'Bearer {access_token}'}
    if body is not None:
        data = json.dumps(body).encode('utf-8')
        headers['Content-Type'] = 'application/json'

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read()
            if not raw:
                return {}
            return json.loads(raw.decode('utf-8', errors='replace'))
    except urllib.error.HTTPError as e:
        code = e.code
        err_body = e.read().decode('utf-8', errors='replace')
        if code == 401:
            print('ERROR: auth expired (401). Run: cal-cli refresh', file=sys.stderr)
            sys.exit(1)
        if code == 403:
            print('ERROR: access denied (403). Check permissions.', file=sys.stderr)
            sys.exit(1)
        if code == 404:
            print('ERROR: not found (404).', file=sys.stderr)
            return None
        if code == 429:
            print('ERROR: rate limited (429). Try again later.', file=sys.stderr)
            return None
        print(f'ERROR: HTTP {code}', file=sys.stderr)
        if debug:
            print(err_body, file=sys.stderr)
        return None
    except urllib.error.URLError as e:
        print(f'ERROR: {e.reason}', file=sys.stderr)
        return None


def api_get(base, endpoint, access_token, debug=False):
    return api_request('GET', base, endpoint, access_token, debug=debug)


def build_query(params):
    """Build an OData query string. Values are URL-encoded, keys are
    not (they are $-prefixed OData system params)."""
    parts = []
    for k, v in params.items():
        parts.append(f'{k}={urllib.parse.quote(str(v), safe="")}')
    return '&'.join(parts)
