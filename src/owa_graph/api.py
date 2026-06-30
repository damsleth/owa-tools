"""HTTP helper for Microsoft Graph and other AAD-backed API audiences."""
import sys
import urllib.parse

from owa_core import http
from owa_core.errors import (
    AuthExpiredError,
    ConflictError,
    InternalError,
    NetworkError,
    NotFoundError,
    OwaError,
    RateLimitedError,
    ScopeInsufficientError,
)

RETRY_AFTER_CAP_SECONDS = http.RETRY_AFTER_CAP_SECONDS
_parse_retry_after = http._parse_retry_after


def _run_request(method, url, access_token, *, body, extra_headers, debug, raw, retry):
    response = http.request(
        method,
        url,
        token=access_token,
        body=body,
        headers=extra_headers,
        retry=retry,
        raw=raw,
        debug=debug,
    )
    return response.bytes if raw else response.json


def api_request(method, base, endpoint, access_token, body=None,
                extra_headers=None, debug=False, raw=False, retry=False):
    """Issue a request against the API at `base`.

    - `base` and `endpoint` are joined with a single slash.
    - `body` is dict-serialised to JSON when non-None; pass `bytes`
      to send raw.
    - `extra_headers` is an optional dict of additional headers.
    - `retry=True` honors `Retry-After` on one 429/503 and retries one
      transport failure.
    - Returns parsed JSON on 2xx (or raw bytes if raw=True), None on
      return-to-caller failures, and exits on auth/permission failures.
    """
    url = f'{base}/{endpoint}' if not endpoint.startswith('http') else endpoint
    try:
        return _run_request(
            method,
            url,
            access_token,
            body=body,
            extra_headers=extra_headers,
            debug=debug,
            raw=raw,
            retry=1 if retry else 0,
        )
    except (AuthExpiredError, ScopeInsufficientError) as error:
        raise error
    except NetworkError as error:
        if retry:
            if debug:
                print(f'DEBUG: {error.message} - retrying once', file=sys.stderr)
            try:
                return _run_request(
                    method,
                    url,
                    access_token,
                    body=body,
                    extra_headers=extra_headers,
                    debug=debug,
                    raw=raw,
                    retry=0,
                )
            except (AuthExpiredError, ScopeInsufficientError) as retry_error:
                raise retry_error
            except OwaError as retry_error:
                raise retry_error
        raise error
    except (ConflictError, InternalError, NotFoundError, RateLimitedError) as error:
        raise error
    except OwaError as error:
        raise error


def paginate(method, url, access_token, extra_headers=None,
             debug=False, retry=False, max_pages=None, on_truncate=None):
    """Yield items from a paginated Graph collection response.

    Walks `@odata.nextLink` until exhausted or `max_pages` reached. The
    caller passes a fully-built first-page URL; subsequent URLs come
    from the server (skiptokens are opaque). Non-collection responses
    (a single entity) yield once and stop.

    When `max_pages` is hit while the server still advertises a
    `@odata.nextLink`, pagination stops early and `on_truncate(pages,
    next_link)` is invoked once (if provided) so the caller can surface a
    truncation signal. Natural exhaustion never fires the callback.
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
            yield page
            return
        pages += 1
        if max_pages is not None and pages >= max_pages:
            if url and on_truncate is not None:
                on_truncate(pages, url)
            return


def api_get(base, endpoint, access_token, extra_headers=None, debug=False, raw=False):
    return api_request('GET', base, endpoint, access_token,
                       extra_headers=extra_headers, debug=debug, raw=raw)


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
