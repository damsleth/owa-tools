"""Drive API v3 HTTP helpers. Content endpoints (`alt=media`, `/export`)
return real bytes, unlike Gmail's base64-in-JSON."""
from urllib.parse import urlencode

from owa_core import http


def _url(base, endpoint, params=None):
    url = f'{base}/{endpoint.lstrip("/")}'
    return f'{url}?{urlencode(params)}' if params else url


def api_get(base, endpoint, access_token, params=None, debug=False):
    return http.request('GET', _url(base, endpoint, params), token=access_token, debug=debug).json


def api_get_bytes(base, endpoint, access_token, params=None, debug=False):
    return http.request(
        'GET', _url(base, endpoint, params), token=access_token, raw=True, debug=debug,
    ).bytes


def paginate(base, endpoint, access_token, params, *, max_pages=None, debug=False):
    """Drive's nextPageToken paging over `files`; returns (items, next_token)."""
    return http.paginate_by_token(
        _url(base, endpoint), token=access_token, list_key='files',
        params=params, max_pages=max_pages, debug=debug,
    )
