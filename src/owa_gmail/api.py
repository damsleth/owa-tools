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
    """Gmail's nextPageToken paging; returns (items, next_page_token_or_None)."""
    return http.paginate_by_token(
        f'{base}/{endpoint.lstrip("/")}', token=access_token, list_key=list_key,
        params=params, max_pages=max_pages, debug=debug,
    )
