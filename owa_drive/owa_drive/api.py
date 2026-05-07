"""Graph HTTP helper for owa-drive.

Two flavours: api_request for JSON in/out (most ops), and
api_request_binary for content endpoints (download/upload). The
4MB upload limit is a Graph constraint - large files need an upload
session, which is a future expansion.
"""
import json
import sys
import urllib.error
import urllib.request

UPLOAD_LIMIT_BYTES = 4 * 1024 * 1024


def _handle_http_error(e, debug, refresh_hint='owa-drive refresh'):
    code = e.code
    err_body = b''
    try:
        err_body = e.read()
    except Exception:
        pass
    if code == 401:
        print(f'ERROR: auth expired (401). Run: {refresh_hint}', file=sys.stderr)
        sys.exit(1)
    if code == 403:
        print(
            'ERROR: access denied (403). The OWA SPA scopes may not '
            'cover this drive item, or the parent folder is restricted.',
            file=sys.stderr,
        )
        if debug:
            print(err_body.decode('utf-8', errors='replace'), file=sys.stderr)
        sys.exit(1)
    if code == 404:
        print('ERROR: not found (404).', file=sys.stderr)
        return None
    if code == 409:
        print('ERROR: conflict (409). The path may already exist.', file=sys.stderr)
        return None
    if code == 413:
        print(
            'ERROR: payload too large (413). Files larger than '
            f'{UPLOAD_LIMIT_BYTES} bytes need an upload session, '
            'which owa-drive does not implement yet.',
            file=sys.stderr,
        )
        return None
    if code == 429:
        print('ERROR: rate limited (429). Try again later.', file=sys.stderr)
        return None
    print(f'ERROR: HTTP {code}', file=sys.stderr)
    if debug:
        print(err_body.decode('utf-8', errors='replace'), file=sys.stderr)
    return None


def api_request(method, base, endpoint, access_token, body=None,
                extra_headers=None, debug=False):
    """JSON in / JSON out (or empty for 204)."""
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
        return _handle_http_error(e, debug)
    except urllib.error.URLError as e:
        print(f'ERROR: {e.reason}', file=sys.stderr)
        return None


def api_get_binary(base, endpoint, access_token, debug=False):
    """GET that returns raw bytes (for /content endpoints)."""
    url = f'{base}/{endpoint.lstrip("/")}'
    if debug:
        print(f'DEBUG: GET {url}', file=sys.stderr)
    req = urllib.request.Request(
        url, headers={'Authorization': f'Bearer {access_token}'}, method='GET',
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        return _handle_http_error(e, debug)
    except urllib.error.URLError as e:
        print(f'ERROR: {e.reason}', file=sys.stderr)
        return None


def api_put_binary(base, endpoint, access_token, content_bytes, debug=False):
    """PUT raw bytes (for small-file content upload)."""
    url = f'{base}/{endpoint.lstrip("/")}'
    if debug:
        print(
            f'DEBUG: PUT {url} ({len(content_bytes)} bytes)',
            file=sys.stderr,
        )
    if len(content_bytes) > UPLOAD_LIMIT_BYTES:
        print(
            f'ERROR: file is {len(content_bytes)} bytes; the simple '
            f'upload path is limited to {UPLOAD_LIMIT_BYTES} bytes. '
            'Larger files need an upload session (not implemented).',
            file=sys.stderr,
        )
        return None
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/octet-stream',
    }
    req = urllib.request.Request(
        url, data=content_bytes, headers=headers, method='PUT',
    )
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read()
            if not raw:
                return {}
            return json.loads(raw.decode('utf-8', errors='replace'))
    except urllib.error.HTTPError as e:
        return _handle_http_error(e, debug)
    except urllib.error.URLError as e:
        print(f'ERROR: {e.reason}', file=sys.stderr)
        return None
