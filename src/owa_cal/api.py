"""Outlook REST HTTP helper for owa-cal."""
from owa_core import http
from owa_core.query import build_query  # noqa: F401  (re-exported for api_mod.build_query)


def api_request(method, base, endpoint, access_token, body=None, debug=False, headers=None):
    """Issue a request against Outlook REST.

    - `base` and `endpoint` are joined with a single slash.
    - `body` is dict-serialised to JSON when non-None.
    - `headers` adds request headers (e.g. `Prefer: outlook.timezone`).
    - Returns parsed JSON on 2xx.
    - Raises typed ``OwaError`` subclasses for expected failures.
    """
    url = f'{base}/{endpoint}'
    return http.request(method, url, token=access_token, body=body, headers=headers, debug=debug).json


def api_get(base, endpoint, access_token, debug=False, headers=None):
    return api_request('GET', base, endpoint, access_token, debug=debug, headers=headers)


def paginate_all(base, endpoint, access_token, debug=False, headers=None):
    """Follow `@odata.nextLink` from the first page until exhausted.

    Builds the first-page URL the same way api_request does, then
    delegates to the shared `owa_core.http.paginate` generator and
    collects every `value` item into a list. Returns the list on
    success. Raises typed ``OwaError`` subclasses for expected failures.
    """
    url = f'{base}/{endpoint}'
    return list(http.paginate(url, token=access_token, headers=headers, debug=debug))


