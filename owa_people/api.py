"""Graph HTTP helper.

One function: api_request. Returns parsed JSON or None for
return-to-caller failures. For 401/403 we exit with a clear message
- owa-people is a CLI, not a library, and there is no recovery path
for an auth failure except telling the user to re-run.
"""
import sys
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


def api_request(method, base, endpoint, access_token, body=None,
                extra_headers=None, debug=False):
    url = f'{base}/{endpoint.lstrip("/")}'
    headers = dict(extra_headers or {})
    try:
        return http.request(
            method, url, token=access_token, body=body, headers=headers, debug=debug,
        ).json
    except (AuthExpiredError, ScopeInsufficientError) as error:
        sys.exit(emit_error(error))
    except (ConflictError, InternalError, NetworkError, NotFoundError, RateLimitedError) as error:
        emit_error(error)
        return None
    except OwaError as error:
        emit_error(error)
        return None


def api_get(base, endpoint, access_token, extra_headers=None, debug=False):
    return api_request('GET', base, endpoint, access_token,
                       extra_headers=extra_headers, debug=debug)


def build_query(params):
    """Build an OData-style query string. Values are URL-encoded."""
    parts = []
    for k, v in params.items():
        parts.append(f'{k}={urllib.parse.quote(str(v), safe="")}')
    return '&'.join(parts)
