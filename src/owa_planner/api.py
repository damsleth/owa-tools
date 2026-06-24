"""Microsoft Graph HTTP helper for owa-planner."""
from owa_core import http
from owa_core.query import build_query
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


def api_request(method, base, endpoint, access_token, body=None, extra_headers=None, debug=False):
    """Issue a request against Microsoft Graph.

    Returns parsed JSON on 2xx (an empty 202/204 body decodes to {}),
    None on recoverable errors (404/429/5xx/conflict), and re-raises on
    401/403 (unrecoverable without reconfig).
    """
    url = f'{base}/{endpoint}'
    headers = dict(extra_headers or {})
    try:
        return http.request(
            method,
            url,
            token=access_token,
            body=body,
            headers=headers,
            debug=debug,
        ).json
    except (AuthExpiredError, ScopeInsufficientError) as error:
        raise error
    except (ConflictError, InternalError, NetworkError, NotFoundError, RateLimitedError) as error:
        raise error
    except OwaError as error:
        raise error


def api_get(base, endpoint, access_token, debug=False):
    return api_request('GET', base, endpoint, access_token, debug=debug)


def api_post(base, endpoint, access_token, body=None, debug=False):
    return api_request('POST', base, endpoint, access_token, body=body, debug=debug)


def api_patch(base, endpoint, access_token, body=None, etag='', debug=False):
    headers = {'If-Match': etag}
    return api_request('PATCH', base, endpoint, access_token, body=body, extra_headers=headers, debug=debug)


def api_delete(base, endpoint, access_token, etag='', debug=False):
    headers = {'If-Match': etag}
    return api_request('DELETE', base, endpoint, access_token, extra_headers=headers, debug=debug)


def paginate_all(base, endpoint, access_token, debug=False):
    """Follow `@odata.nextLink` from the first page until exhausted.

    Builds the first-page URL the same way api_request does, then delegates
    to the shared `owa_core.http.paginate` generator and collects every
    `value` item. Returns the list on success, or None on the recoverable
    errors api_request maps to None (auth/scope re-raise).
    """
    url = f'{base}/{endpoint}'
    try:
        return list(http.paginate(url, token=access_token, debug=debug))
    except (AuthExpiredError, ScopeInsufficientError) as error:
        raise error
    except (ConflictError, InternalError, NetworkError, NotFoundError, RateLimitedError) as error:
        raise error
    except OwaError as error:
        raise error


