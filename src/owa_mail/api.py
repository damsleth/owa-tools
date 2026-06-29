"""Outlook REST HTTP helper for owa-mail."""
from owa_core import http
from owa_core import upload as upload_mod
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
from owa_core.query import build_query  # noqa: F401  (re-exported for api_mod.build_query)


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
        raise error
    except (ConflictError, InternalError, NetworkError, NotFoundError, RateLimitedError) as error:
        raise error
    except OwaError as error:
        raise error


def api_get(base, endpoint, access_token, debug=False):
    return api_request('GET', base, endpoint, access_token, debug=debug)


def paginate_all(base, endpoint, access_token, extra_headers=None, debug=False):
    """Follow `@odata.nextLink` from the first page until exhausted.

    Builds the first-page URL from `base`/`endpoint` (the same join
    api_request uses), then delegates to the shared
    `owa_core.http.paginate` generator and collects every `value` item
    into a list. Returns the list on success, or None on the recoverable
    errors that api_request maps to None (auth/scope errors re-raise so
    the caller's top-level handler can act on them), matching the
    single-page error contract.
    """
    url = f'{base}/{endpoint}'
    try:
        return list(http.paginate(
            url, token=access_token, headers=extra_headers, debug=debug,
        ))
    except (AuthExpiredError, ScopeInsufficientError) as error:
        raise error
    except OwaError as error:
        raise error


def api_get_binary(base, endpoint, access_token, debug=False):
    """GET that returns raw bytes (for attachment `$value` endpoints).

    Returns the bytes on 2xx, None on the recoverable errors that
    api_request maps to None, and re-raises auth/scope errors.
    """
    url = f'{base}/{endpoint}'
    try:
        return http.request(
            'GET', url, token=access_token, raw=True, debug=debug,
        ).bytes
    except (AuthExpiredError, ScopeInsufficientError) as error:
        raise error
    except OwaError as error:
        raise error


def api_upload_attachment_session(base, session_endpoint, access_token,
                                  session_body, content_bytes, debug=False):
    """Attach a large file to a (draft) message via an upload session.

    Creates the upload session against `session_endpoint`
    (`me/messages/{id}/attachments/createUploadSession`), then hands the
    pre-authorized uploadUrl and the bytes to the generic
    owa_core.upload.upload_session driver. Returns the final attachment
    JSON, or None if session creation surfaced a recoverable OwaError
    (matching the api_request None contract).
    """
    url = f'{base}/{session_endpoint}'
    try:
        session = http.request(
            'POST', url, token=access_token, body=session_body, debug=debug,
        ).json
    except (AuthExpiredError, ScopeInsufficientError) as error:
        raise error
    except OwaError as error:
        raise error
    if not isinstance(session, dict):
        emit_error(InternalError('attachment upload session returned no body'))
        return None
    upload_url = session.get('uploadUrl') or session.get('UploadUrl')
    if not upload_url:
        emit_error(InternalError('attachment upload session had no uploadUrl'))
        return None
    try:
        return upload_mod.upload_session(upload_url, content_bytes, debug=debug)
    except (AuthExpiredError, ScopeInsufficientError) as error:
        raise error
    except OwaError as error:
        raise error


