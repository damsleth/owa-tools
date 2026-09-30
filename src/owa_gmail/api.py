"""Gmail API v1 HTTP helpers. The base is per-user (.../users/me), so every
endpoint is already scoped to the signed-in account."""

from owa_core import http
from owa_core import query as query_mod


def _url(base, endpoint, params=None):
    url = f'{base}/{endpoint.lstrip("/")}'
    if params:
        url += '?' + query_mod.build_query(params)
    return url


def api_get(base, endpoint, access_token, params=None, debug=False, retry=0):
    return http.request(
        'GET', _url(base, endpoint, params), token=access_token, retry=retry, debug=debug,
    ).json


def paginate(base, endpoint, access_token, params, list_key, *, max_pages=None, debug=False):
    """Follow Gmail's `nextPageToken` (not Graph's @odata.nextLink) and collect
    every `list_key` item. Returns (items, next_page_token_or_None)."""
    items = []
    page_params = dict(params or {})
    pages = 0
    while True:
        payload = api_get(base, endpoint, access_token, params=page_params, debug=debug) or {}
        items.extend(payload.get(list_key) or [])
        token = payload.get('nextPageToken')
        pages += 1
        if not token or (max_pages is not None and pages >= max_pages):
            return items, token
        page_params = dict(page_params, pageToken=token)
