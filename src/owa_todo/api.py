"""Outlook REST HTTP helper for owa-todo."""
from owa_core import http
from owa_core.query import build_query  # noqa: F401  (re-exported for api_mod.build_query)


def api_request(method, base, endpoint, access_token, body=None, debug=False):
    """Issue a request against Outlook REST.

    Returns parsed JSON on 2xx (an empty 202/204 body decodes to {}).
    Raises typed ``OwaError`` subclasses for expected failures.
    """
    url = f'{base}/{endpoint}'
    return http.request(method, url, token=access_token, body=body, debug=debug).json


def api_get(base, endpoint, access_token, debug=False):
    return api_request('GET', base, endpoint, access_token, debug=debug)


def paginate_all(base, endpoint, access_token, debug=False):
    """Follow `@odata.nextLink` from the first page until exhausted.

    Builds the first-page URL the same way api_request does, then
    delegates to the shared `owa_core.http.paginate` generator and
    collects every `value` item. Returns the list on success. Raises
    typed ``OwaError`` subclasses for expected failures.
    """
    url = f'{base}/{endpoint}'
    return list(http.paginate(url, token=access_token, debug=debug))


