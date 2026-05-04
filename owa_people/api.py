"""Graph HTTP helper.

One function: api_request. Returns parsed JSON or None for
return-to-caller failures. For 401/403 we exit with a clear message
- owa-people is a CLI, not a library, and there is no recovery path
for an auth failure except telling the user to re-run.
"""
import json
import sys
import urllib.error
import urllib.parse
import urllib.request


def api_request(method, base, endpoint, access_token, body=None,
                extra_headers=None, debug=False):
    url = f'{base}/{endpoint.lstrip("/")}'
    if debug:
        print(f'DEBUG: {method} {url}', file=sys.stderr)
        if body is not None:
            print(f'DEBUG: body: {json.dumps(body)[:500]}', file=sys.stderr)

    headers = {'Authorization': f'Bearer {access_token}'}
    if extra_headers:
        headers.update(extra_headers)
    data = None
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
            print('ERROR: auth expired (401). Run: owa-people refresh', file=sys.stderr)
            sys.exit(1)
        if code == 403:
            print(
                'ERROR: access denied (403). The OWA SPA scopes may not cover '
                'this Graph endpoint - try owa-graph with --audience graph for '
                'a finer-grained probe.',
                file=sys.stderr,
            )
            if debug:
                print(err_body, file=sys.stderr)
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


def api_get(base, endpoint, access_token, extra_headers=None, debug=False):
    return api_request('GET', base, endpoint, access_token,
                       extra_headers=extra_headers, debug=debug)


def build_query(params):
    """Build an OData-style query string. Values are URL-encoded."""
    parts = []
    for k, v in params.items():
        parts.append(f'{k}={urllib.parse.quote(str(v), safe="")}')
    return '&'.join(parts)
