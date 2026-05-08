"""Outlook REST HTTP helper.

One function: api_request. Returns parsed JSON or None (for
return-to-caller failures). For auth/permission failures we exit the
process with a clear message - owa-cal is a CLI, not a library, and
there is no recovery path for a 401 except telling the user to re-run.
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


def api_request(method, base, endpoint, access_token, body=None, debug=False):
    """Issue a request against Outlook REST.

    - `base` and `endpoint` are joined with a single slash.
    - `body` is dict-serialised to JSON when non-None.
    - Returns parsed JSON on 2xx, None on 404/429 (caller decides),
      and exits on 401/403 (unrecoverable without reconfig).
    """
    url = f'{base}/{endpoint}'
    try:
        return http.request(method, url, token=access_token, body=body, debug=debug).json
    except (AuthExpiredError, ScopeInsufficientError) as error:
        sys.exit(emit_error(error))
    except (ConflictError, InternalError, NetworkError, NotFoundError, RateLimitedError) as error:
        emit_error(error)
        return None
    except OwaError as error:
        emit_error(error)
        return None


def api_get(base, endpoint, access_token, debug=False):
    return api_request('GET', base, endpoint, access_token, debug=debug)


def build_query(params):
    """Build an OData query string. Values are URL-encoded, keys are
    not (they are $-prefixed OData system params)."""
    parts = []
    for k, v in params.items():
        parts.append(f'{k}={urllib.parse.quote(str(v), safe="")}')
    return '&'.join(parts)
