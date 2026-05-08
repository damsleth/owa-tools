"""Graph HTTP helper for owa-drive.

Two flavours: api_request for JSON in/out (most ops), and
api_request_binary for content endpoints (download/upload). The
4MB upload limit is a Graph constraint - large files need an upload
session, which is a future expansion.
"""
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

UPLOAD_LIMIT_BYTES = 4 * 1024 * 1024


def _handle_owa_error(error):
    if isinstance(error, (AuthExpiredError, ScopeInsufficientError)):
        sys.exit(emit_error(error))
    if isinstance(error, (ConflictError, InternalError, NetworkError, NotFoundError, RateLimitedError)):
        emit_error(error)
        return None
    if isinstance(error, OwaError):
        emit_error(error)
        return None
    raise error


def api_request(method, base, endpoint, access_token, body=None,
                extra_headers=None, debug=False):
    """JSON in / JSON out (or empty for 204)."""
    url = f'{base}/{endpoint.lstrip("/")}'
    headers = dict(extra_headers or {})
    try:
        return http.request(
            method, url, token=access_token, body=body, headers=headers, debug=debug,
        ).json
    except OwaError as error:
        return _handle_owa_error(error)


def api_get_binary(base, endpoint, access_token, debug=False):
    """GET that returns raw bytes (for /content endpoints)."""
    url = f'{base}/{endpoint.lstrip("/")}'
    try:
        return http.request(
            'GET', url, token=access_token, raw=True, debug=debug,
        ).bytes
    except OwaError as error:
        return _handle_owa_error(error)


def api_put_binary(base, endpoint, access_token, content_bytes, debug=False):
    """PUT raw bytes (for small-file content upload)."""
    url = f'{base}/{endpoint.lstrip("/")}'
    if debug:
        print(
            f'DEBUG: PUT {url} ({len(content_bytes)} bytes)',
            file=sys.stderr,
        )
    if len(content_bytes) > UPLOAD_LIMIT_BYTES:
        print(
            f'ERROR: file is {len(content_bytes)} bytes; the simple '
            f'upload path is limited to {UPLOAD_LIMIT_BYTES} bytes. '
            'Larger files need an upload session (not implemented).',
            file=sys.stderr,
        )
        return None
    try:
        return http.request(
            'PUT',
            url,
            token=access_token,
            body=content_bytes,
            headers={'Content-Type': 'application/octet-stream'},
            debug=debug,
        ).json
    except OwaError as error:
        return _handle_owa_error(error)
