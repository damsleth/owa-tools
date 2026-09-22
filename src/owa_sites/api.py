"""SharePoint REST HTTP helper for owa-sites.

Mirrors owa_todo/api.py but targets the SharePoint REST API on the per-tenant
`*.sharepoint.com` host. Sends `Accept: application/json;odata=nometadata` so
responses come back as clean JSON (no inline `__metadata`). Failures raise
typed ``OwaError`` subclasses so the dispatcher maps them to the shared
exit-code taxonomy.
"""
from owa_core import http

ACCEPT_JSON = 'application/json;odata=nometadata'


def sp_request(method, base, endpoint, access_token, body=None, debug=False):
    """Issue a request against the SharePoint REST API.

    Returns parsed JSON on 2xx. Raises typed ``OwaError`` subclasses for
    expected failures.
    """
    url = f'{base}/{endpoint}'
    return http.request(
        method, url, token=access_token, body=body,
        headers={'Accept': ACCEPT_JSON}, debug=debug,
    ).json


def sp_get(base, endpoint, access_token, debug=False):
    return sp_request('GET', base, endpoint, access_token, debug=debug)


def paginate_sp(base, endpoint, access_token, debug=False, max_pages=50, on_truncate=None):
    """Follow SharePoint REST `odata.nextLink` from the first page until exhausted.

    SharePoint's `odata=nometadata` next link is the bare `odata.nextLink` key
    (no `@`), so the shared Graph paginator does not apply. Returns the combined
    `value` list on success. Raises typed ``OwaError`` subclasses for
    expected failures.

    `max_pages=None` follows every page (the `--all` path). When a numeric cap
    trips while the server still advertises a next link, `on_truncate(pages,
    next_link)` fires once (if provided) so the caller can surface a truncation
    signal. Natural exhaustion never fires it.
    """
    url = f'{base}/{endpoint}'
    items = []
    pages = 0
    while url:
        resp = http.request(
            'GET', url, token=access_token, headers={'Accept': ACCEPT_JSON}, debug=debug,
        )
        payload = resp.json if isinstance(resp.json, dict) else {}
        value = payload.get('value')
        if not isinstance(value, list):
            return [payload] if payload else []
        items.extend(value)
        url = payload.get('odata.nextLink') or payload.get('@odata.nextLink')
        pages += 1
        if max_pages is not None and pages >= max_pages:
            if url and on_truncate is not None:
                on_truncate(pages, url)
            break
    return items
