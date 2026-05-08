"""Graph HTTP helper. Same shape as owa-people/owa-cal."""
import sys

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


def api_post(base, endpoint, access_token, body=None, extra_headers=None, debug=False):
    return api_request('POST', base, endpoint, access_token,
                       body=body, extra_headers=extra_headers, debug=debug)
