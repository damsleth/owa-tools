"""Outlook REST HTTP helper for owa-todo.

Mirrors owa_cal/api.py: one request function plus a paginating reader.
Returns parsed JSON or None for recoverable failures; auth/scope errors
re-raise so the dispatcher maps them to the shared exit-code taxonomy.
"""
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
    emit_error,
)


def api_request(method, base, endpoint, access_token, body=None, debug=False):
    """Issue a request against Outlook REST.

    Returns parsed JSON on 2xx (an empty 202/204 body decodes to {}),
    None on recoverable errors (404/429/5xx/conflict), and re-raises on
    401/403 (unrecoverable without reconfig).
    """
    url = f'{base}/{endpoint}'
    try:
        return http.request(method, url, token=access_token, body=body, debug=debug).json
    except (AuthExpiredError, ScopeInsufficientError) as error:
        raise error
    except (ConflictError, InternalError, NetworkError, NotFoundError, RateLimitedError) as error:
        emit_error(error)
        return None
    except OwaError as error:
        emit_error(error)
        return None


def api_get(base, endpoint, access_token, debug=False):
    return api_request('GET', base, endpoint, access_token, debug=debug)


def paginate_all(base, endpoint, access_token, debug=False):
    """Follow `@odata.nextLink` from the first page until exhausted.

    Builds the first-page URL the same way api_request does, then
    delegates to the shared `owa_core.http.paginate` generator and
    collects every `value` item. Returns the list on success, or None on
    the recoverable errors api_request maps to None (auth/scope re-raise).
    """
    url = f'{base}/{endpoint}'
    try:
        return list(http.paginate(url, token=access_token, debug=debug))
    except (AuthExpiredError, ScopeInsufficientError) as error:
        raise error
    except (ConflictError, InternalError, NetworkError, NotFoundError, RateLimitedError) as error:
        emit_error(error)
        return None
    except OwaError as error:
        emit_error(error)
        return None


def build_query(params):
    """Build an OData query string. Values are URL-encoded; keys are not
    (they are $-prefixed OData system params)."""
    parts = []
    for k, v in params.items():
        parts.append(f'{k}={urllib.parse.quote(str(v), safe="")}')
    return '&'.join(parts)
