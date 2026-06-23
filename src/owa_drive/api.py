"""Graph HTTP helper for owa-drive.

Two flavours: api_request for JSON in/out (most ops), and
api_request_binary for content endpoints (download/upload). Files at or
under UPLOAD_LIMIT_BYTES use the simple single-PUT path
(api_put_binary); larger files go through a Graph resumable upload
session driven by the generic owa_core.upload helper.
"""
import sys

from owa_core import http
from owa_core import upload as upload_mod
from owa_core.errors import InternalError, OwaError, emit_error

UPLOAD_LIMIT_BYTES = 4 * 1024 * 1024


def _handle_owa_error(error):
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


def paginate_all(base, endpoint, access_token, extra_headers=None, debug=False):
    """Follow `@odata.nextLink` from the first page until exhausted.

    Builds the first-page URL the same way api_request does, then
    delegates to the shared `owa_core.http.paginate` generator and
    collects every `value` item into a list. Returns the list on
    success, or None on the recoverable errors api_request maps to None
    (auth/scope errors re-raise), matching the single-page contract.
    """
    url = f'{base}/{endpoint.lstrip("/")}'
    headers = dict(extra_headers or {})
    try:
        return list(http.paginate(
            url, token=access_token, headers=headers, debug=debug,
        ))
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
    """PUT raw bytes in a single request (small-file content upload).

    Graph caps the simple PUT path at UPLOAD_LIMIT_BYTES. Callers must
    route larger payloads through api_upload_session; this function
    defends the boundary so a misroute fails loudly rather than 4xx-ing
    against Graph.
    """
    url = f'{base}/{endpoint.lstrip("/")}'
    if debug:
        print(
            f'DEBUG: PUT {url} ({len(content_bytes)} bytes)',
            file=sys.stderr,
        )
    if len(content_bytes) > UPLOAD_LIMIT_BYTES:
        raise InternalError(
            f'file is {len(content_bytes)} bytes; the simple upload path is '
            f'limited to {UPLOAD_LIMIT_BYTES} bytes. Use api_upload_session '
            'for larger files.',
        )
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


def api_upload_session(base, session_endpoint, access_token, content_bytes,
                       debug=False, chunk_size=upload_mod.DEFAULT_CHUNK_SIZE):
    """Upload arbitrary-size bytes via a Graph resumable upload session.

    Creates an upload session against `session_endpoint`
    (e.g. `me/drive/root:/path:/createUploadSession`), then hands the
    pre-authorized uploadUrl and the bytes to the generic
    owa_core.upload.upload_session driver. Returns the final driveItem
    JSON, or None if session creation surfaced a recoverable OwaError
    (matching the api_request None contract).
    """
    url = f'{base}/{session_endpoint.lstrip("/")}'
    body = {'item': {'@microsoft.graph.conflictBehavior': 'replace'}}
    try:
        session = http.request(
            'POST', url, token=access_token, body=body, debug=debug,
        ).json
    except OwaError as error:
        return _handle_owa_error(error)
    if not isinstance(session, dict):
        emit_error(InternalError('upload session creation returned no body'))
        return None
    upload_url = session.get('uploadUrl')
    if not upload_url:
        emit_error(InternalError('upload session response had no uploadUrl'))
        return None
    if debug:
        print('DEBUG: created upload session', file=sys.stderr)
    try:
        return upload_mod.upload_session(
            upload_url, content_bytes, chunk_size=chunk_size, debug=debug,
        )
    except OwaError as error:
        return _handle_owa_error(error)
