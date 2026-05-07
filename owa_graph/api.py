"""HTTP helper for Microsoft Graph (and any other API behind an AAD
audience).

`api_request` returns parsed JSON or None for return-to-caller failures.
For auth/permission failures we exit the process with a clear message -
owa-graph is a CLI, not a library, and there is no recovery path for a
401 except telling the user to re-run.
"""
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# Cap on Retry-After honoring. Servers can legitimately ask for hours;
# a CLI invocation that sleeps that long is broken UX. We honor up to
# this many seconds, then surface the rate-limit as a normal failure.
RETRY_AFTER_CAP_SECONDS = 60


def _parse_retry_after(value, default=2):
    """Parse a Retry-After header. RFC 7231 allows seconds (`120`) or
    HTTP-date (`Wed, 21 Oct 2026 07:28:00 GMT`). We honor seconds and
    fall back to `default` for date form (rare on Graph)."""
    if not value:
        return default
    try:
        return max(0, int(value.strip()))
    except (TypeError, ValueError):
        return default


def api_request(method, base, endpoint, access_token, body=None,
                extra_headers=None, debug=False, raw=False, retry=False):
    """Issue a request against the API at `base`.

    - `base` and `endpoint` are joined with a single slash.
    - `body` is dict-serialised to JSON when non-None; pass a `bytes`
      object to send raw.
    - `extra_headers` is an optional dict of additional headers.
    - `retry=True` honors `Retry-After` on a single 429/503; further
      failures surface as None.
    - Returns parsed JSON on 2xx (or raw bytes if raw=True),
      None on 404/429 (caller decides), and exits on 401/403
      (unrecoverable without reconfig).
    """
    url = f'{base}/{endpoint}' if not endpoint.startswith('http') else endpoint
    if debug:
        print(f'DEBUG: {method} {url}', file=sys.stderr)
        if body is not None and not isinstance(body, (bytes, bytearray)):
            print(f'DEBUG: body: {json.dumps(body)[:500]}', file=sys.stderr)

    data = None
    headers = {'Authorization': f'Bearer {access_token}'}
    if body is not None:
        if isinstance(body, (bytes, bytearray)):
            data = bytes(body)
        else:
            data = json.dumps(body).encode('utf-8')
            headers['Content-Type'] = 'application/json'
    if extra_headers:
        for k, v in extra_headers.items():
            headers[k] = v

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            payload = resp.read()
            if raw:
                return payload
            if not payload:
                return {}
            return json.loads(payload.decode('utf-8', errors='replace'))
    except urllib.error.HTTPError as e:
        code = e.code
        err_body = e.read().decode('utf-8', errors='replace')
        if code == 401:
            print('ERROR: auth expired (401). Run: owa-graph refresh', file=sys.stderr)
            sys.exit(1)
        if code == 403:
            print('ERROR: access denied (403). Check permissions/scopes.', file=sys.stderr)
            if debug:
                print(err_body, file=sys.stderr)
            sys.exit(1)
        if code == 404:
            print('ERROR: not found (404).', file=sys.stderr)
            return None
        if code in (429, 503) and retry:
            wait = _parse_retry_after(e.headers.get('Retry-After'))
            if wait > RETRY_AFTER_CAP_SECONDS:
                print(
                    f'ERROR: rate limited ({code}); server asked for {wait}s '
                    f'(>cap {RETRY_AFTER_CAP_SECONDS}s). Try again later.',
                    file=sys.stderr,
                )
                return None
            if debug:
                print(f'DEBUG: {code} - retrying in {wait}s', file=sys.stderr)
            time.sleep(wait)
            return api_request(
                method, base, endpoint, access_token,
                body=body, extra_headers=extra_headers,
                debug=debug, raw=raw, retry=False,
            )
        if code == 429:
            print('ERROR: rate limited (429). Try again later.', file=sys.stderr)
            return None
        if code == 503:
            print('ERROR: service unavailable (503). Try again later.', file=sys.stderr)
            return None
        print(f'ERROR: HTTP {code}', file=sys.stderr)
        if debug:
            print(err_body, file=sys.stderr)
        return None
    except urllib.error.URLError as e:
        if retry:
            # Single retry on transport-level failures (e.g. connection
            # reset between pages of a long --all walk). Bounded - we
            # disable retry on the second attempt so a persistently
            # broken host still surfaces as an error.
            if debug:
                print(f'DEBUG: URLError {e.reason!r} - retrying once', file=sys.stderr)
            try:
                return api_request(
                    method, base, endpoint, access_token,
                    body=body, extra_headers=extra_headers,
                    debug=debug, raw=raw, retry=False,
                )
            except Exception:  # pragma: no cover - defensive
                pass
        print(f'ERROR: {e.reason}', file=sys.stderr)
        return None


def paginate(method, url, access_token, extra_headers=None,
             debug=False, retry=False, max_pages=None):
    """Yield items from a paginated Graph collection response.

    Walks `@odata.nextLink` until exhausted or `max_pages` reached. The
    caller passes a fully-built first-page URL; subsequent URLs come
    from the server (skiptokens are opaque). Non-collection responses
    (a single entity) yield once and stop.

    Yields one item at a time so callers can stream to stdout without
    holding the full result set in memory.
    """
    pages = 0
    while url:
        page = api_request(
            method, '', url, access_token,
            extra_headers=extra_headers, debug=debug, retry=retry,
        )
        if page is None:
            return
        if isinstance(page, dict) and isinstance(page.get('value'), list):
            for item in page['value']:
                yield item
            url = page.get('@odata.nextLink')
        else:
            # Single entity, not a collection - yield once and stop.
            yield page
            return
        pages += 1
        if max_pages is not None and pages >= max_pages:
            return


def api_get(base, endpoint, access_token, extra_headers=None, debug=False, raw=False):
    return api_request('GET', base, endpoint, access_token,
                       extra_headers=extra_headers, debug=debug, raw=raw)


def build_query(params):
    """Build an OData query string. Values are URL-encoded, keys are
    not (they are $-prefixed OData system params)."""
    parts = []
    for k, v in params.items():
        parts.append(f'{k}={urllib.parse.quote(str(v), safe="")}')
    return '&'.join(parts)


def build_url(base, path, query_pairs=None):
    """Join base + path and append a URL-encoded query string.

    `path` may include or omit a leading slash, and may already contain
    its own `?...` query - in which case `query_pairs` are appended with
    `&`. `query_pairs` is an iterable of `(key, value)` tuples; we keep
    it as tuples (not a dict) so the same key can repeat (`$filter` etc.
    only allow one, but the parser shouldn't enforce that here).
    """
    base = base.rstrip('/')
    has_q = '?' in path
    path = path.lstrip('/')
    url = f'{base}/{path}'
    if not query_pairs:
        return url
    encoded = '&'.join(
        f'{k}={urllib.parse.quote(str(v), safe="")}' for k, v in query_pairs
    )
    sep = '&' if has_q else '?'
    return f'{url}{sep}{encoded}'
