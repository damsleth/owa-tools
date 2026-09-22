"""Graph HTTP helper for owa-people."""
from owa_core import http
from owa_core.query import build_query  # noqa: F401  (re-exported for cli.py)


def api_request(method, base, endpoint, access_token, body=None,
                extra_headers=None, debug=False):
    url = f'{base}/{endpoint.lstrip("/")}'
    headers = dict(extra_headers or {})
    return http.request(
        method, url, token=access_token, body=body, headers=headers, debug=debug,
    ).json


def api_get(base, endpoint, access_token, extra_headers=None, debug=False):
    return api_request('GET', base, endpoint, access_token,
                       extra_headers=extra_headers, debug=debug)


def api_get_binary(base, endpoint, access_token, extra_headers=None, debug=False):
    """GET that returns raw bytes (for $value endpoints like a photo).

    Raises OwaError on failure, matching the rest of the suite's binary
    helpers (see owa_drive.api.api_get_binary).
    """
    url = f'{base}/{endpoint.lstrip("/")}'
    headers = dict(extra_headers or {})
    return http.request(
        'GET', url, token=access_token, headers=headers, raw=True, debug=debug,
    ).bytes


def paginate_all(base, endpoint, access_token, extra_headers=None, debug=False):
    """Follow `@odata.nextLink` from the first page until exhausted.

    Builds the first-page URL the same way api_request does, then
    delegates to the shared `owa_core.http.paginate` generator and
    collects every `value` item into a list. Returns the list on
    success. Raises typed ``OwaError`` subclasses for expected failures.
    """
    url = f'{base}/{endpoint.lstrip("/")}'
    return list(http.paginate(
        url, token=access_token, headers=dict(extra_headers or {}), debug=debug,
    ))


