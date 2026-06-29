"""Graph HTTP helper for owa-people."""
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
from owa_core.query import build_query  # noqa: F401  (re-exported for cli.py)


def api_request(method, base, endpoint, access_token, body=None,
                extra_headers=None, debug=False):
    url = f'{base}/{endpoint.lstrip("/")}'
    headers = dict(extra_headers or {})
    try:
        return http.request(
            method, url, token=access_token, body=body, headers=headers, debug=debug,
        ).json
    except (AuthExpiredError, ScopeInsufficientError) as error:
        raise error
    except (ConflictError, InternalError, NetworkError, NotFoundError, RateLimitedError) as error:
        raise error
    except OwaError as error:
        raise error


def api_get(base, endpoint, access_token, extra_headers=None, debug=False):
    return api_request('GET', base, endpoint, access_token,
                       extra_headers=extra_headers, debug=debug)


def paginate_all(base, endpoint, access_token, extra_headers=None, debug=False):
    """Follow `@odata.nextLink` from the first page until exhausted.

    Builds the first-page URL the same way api_request does, then
    delegates to the shared `owa_core.http.paginate` generator and
    collects every `value` item into a list. Returns the list on
    success, or None on the recoverable errors api_request maps to None
    (auth/scope errors re-raise), matching the single-page contract.
    """
    url = f'{base}/{endpoint.lstrip("/")}'
    try:
        return list(http.paginate(
            url, token=access_token, headers=dict(extra_headers or {}), debug=debug,
        ))
    except (AuthExpiredError, ScopeInsufficientError) as error:
        raise error
    except OwaError as error:
        raise error


