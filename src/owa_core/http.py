"""Shared HTTP helpers for Microsoft 365 APIs."""
import json
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from .errors import (
    AuthExpiredError,
    ConflictError,
    InternalError,
    NetworkError,
    NotFoundError,
    RateLimitedError,
    ScopeInsufficientError,
)
from .secrets import redact

RETRY_AFTER_CAP_SECONDS = 60


@dataclass(frozen=True)
class Response:
    status: int
    headers: dict
    json: object | None
    bytes: bytes
    next_link: str | None = None
    request_id: str | None = None


def _headers_dict(headers):
    if headers is None:
        return {}
    if hasattr(headers, 'items'):
        return {str(key): str(value) for key, value in headers.items()}
    return {}


def _parse_retry_after(value, default=2):
    if not value:
        return default
    try:
        return max(0, int(str(value).strip()))
    except (TypeError, ValueError):
        return default


def _request_id(headers):
    for key in ('request-id', 'client-request-id', 'x-ms-ags-diagnostic'):
        if key in headers:
            return headers[key]
        title = key.title()
        if title in headers:
            return headers[title]
    return None


def _read_error_body(error):
    try:
        return error.read().decode('utf-8', errors='replace')
    except Exception:
        return ''


def _raise_for_http_error(error, *, debug=False):
    status = error.code
    headers = _headers_dict(getattr(error, 'headers', None))
    body = redact(_read_error_body(error))
    if status == 401:
        raise AuthExpiredError('auth expired (401)', remediation='Run owa-piggy setup')
    if status == 403:
        raise ScopeInsufficientError('access denied (403)')
    if status == 404:
        raise NotFoundError('not found (404)')
    if status in (409, 412):
        raise ConflictError(f'conflict ({status})')
    if status == 429:
        raise RateLimitedError('rate limited (429)')
    if status >= 500:
        raise NetworkError(f'service unavailable ({status})')
    message = f'HTTP {status}'
    if debug and body:
        message = f'{message}: {body}'
    if headers:
        request_id = _request_id(headers)
        if request_id:
            message = f'{message} request_id={request_id}'
    raise InternalError(message)


def _decode_response(raw, *, raw_mode):
    if raw_mode:
        return None
    if not raw:
        return {}
    try:
        return json.loads(raw.decode('utf-8', errors='replace'))
    except json.JSONDecodeError as exc:
        raise InternalError('HTTP response was not valid JSON', cause=exc)


def request(
    method,
    url,
    *,
    token,
    body=None,
    headers=None,
    timeout=30,
    retry=0,
    raw=False,
    debug=False,
    sleep=time.sleep,
    urlopen=urllib.request.urlopen,
):
    """Issue one HTTP request and return a Response or raise OwaError."""
    all_headers = {'Authorization': f'Bearer {token}'}
    if headers:
        all_headers.update(headers)
    data = None
    if body is not None:
        if isinstance(body, (bytes, bytearray)):
            data = bytes(body)
        else:
            data = json.dumps(body).encode('utf-8')
            all_headers.setdefault('Content-Type', 'application/json')
    if debug:
        print(f'DEBUG: {method} {url}', file=sys.stderr)
        if body is not None and not isinstance(body, (bytes, bytearray)):
            print(f'DEBUG: body: {redact(json.dumps(body))[:500]}', file=sys.stderr)

    req = urllib.request.Request(url, data=data, headers=all_headers, method=method)
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw_bytes = resp.read()
            resp_headers = _headers_dict(getattr(resp, 'headers', None))
            payload = _decode_response(raw_bytes, raw_mode=raw)
            next_link = payload.get('@odata.nextLink') if isinstance(payload, dict) else None
            return Response(
                status=getattr(resp, 'status', getattr(resp, 'code', 200)),
                headers=resp_headers,
                json=payload,
                bytes=raw_bytes,
                next_link=next_link,
                request_id=_request_id(resp_headers),
            )
    except urllib.error.HTTPError as error:
        if error.code in (429, 503) and retry > 0:
            wait = _parse_retry_after(getattr(error, 'headers', {}).get('Retry-After'))
            if wait <= RETRY_AFTER_CAP_SECONDS:
                if debug:
                    print(f'DEBUG: {error.code} - retrying in {wait}s', file=sys.stderr)
                sleep(wait)
                return request(
                    method,
                    url,
                    token=token,
                    body=body,
                    headers=headers,
                    timeout=timeout,
                    retry=retry - 1,
                    raw=raw,
                    debug=debug,
                    sleep=sleep,
                    urlopen=urlopen,
                )
            raise RateLimitedError(
                f'rate limited ({error.code}); server asked for {wait}s '
                f'(>cap {RETRY_AFTER_CAP_SECONDS}s). Try again later.',
            )
        _raise_for_http_error(error, debug=debug)
    except urllib.error.URLError as exc:
        raise NetworkError(f'network error: {exc.reason}', cause=exc)


def request_unauthenticated(
    method,
    url,
    *,
    body=None,
    headers=None,
    timeout=30,
    retry=0,
    debug=False,
    sleep=time.sleep,
    urlopen=urllib.request.urlopen,
):
    """Issue one HTTP request WITHOUT an Authorization header.

    Used for pre-signed URLs (e.g. Graph upload-session `uploadUrl`s)
    where attaching a bearer token would break the request. Returns a
    Response and applies the same 429/503 Retry-After handling as
    `request`, but never decodes JSON automatically - the caller reads
    `Response.bytes` (and may parse). Raises OwaError subclasses, mapping
    transport errors to NetworkError and HTTP error statuses to the
    shared typed errors. Successful statuses (including 202 Accepted)
    are returned as-is so callers can drive multi-step protocols.
    """
    all_headers = dict(headers or {})
    data = bytes(body) if isinstance(body, (bytes, bytearray)) else body
    if debug:
        print(f'DEBUG: {method} {url} (unauthenticated)', file=sys.stderr)
    req = urllib.request.Request(url, data=data, headers=all_headers, method=method)
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw_bytes = resp.read()
            resp_headers = _headers_dict(getattr(resp, 'headers', None))
            return Response(
                status=getattr(resp, 'status', getattr(resp, 'code', 200)),
                headers=resp_headers,
                json=None,
                bytes=raw_bytes,
                request_id=_request_id(resp_headers),
            )
    except urllib.error.HTTPError as error:
        if error.code in (429, 503) and retry > 0:
            wait = _parse_retry_after(_headers_dict(getattr(error, 'headers', None)).get('Retry-After'))
            if wait <= RETRY_AFTER_CAP_SECONDS:
                if debug:
                    print(f'DEBUG: {error.code} - retrying in {wait}s', file=sys.stderr)
                sleep(wait)
                return request_unauthenticated(
                    method,
                    url,
                    body=body,
                    headers=headers,
                    timeout=timeout,
                    retry=retry - 1,
                    debug=debug,
                    sleep=sleep,
                    urlopen=urlopen,
                )
            raise RateLimitedError(
                f'rate limited ({error.code}); server asked for {wait}s '
                f'(>cap {RETRY_AFTER_CAP_SECONDS}s). Try again later.',
            )
        _raise_for_http_error(error, debug=debug)
    except urllib.error.URLError as exc:
        raise NetworkError(f'network error: {exc.reason}', cause=exc)


def paginate(
    first_url,
    *,
    token,
    headers=None,
    retry=0,
    max_pages=None,
    debug=False,
    urlopen=urllib.request.urlopen,
    sleep=time.sleep,
):
    """Yield items from Graph-style `value` pages."""
    pages = 0
    url = first_url
    while url:
        response = request(
            'GET',
            url,
            token=token,
            headers=headers,
            retry=retry,
            debug=debug,
            urlopen=urlopen,
            sleep=sleep,
        )
        payload = response.json
        if isinstance(payload, dict) and isinstance(payload.get('value'), list):
            for item in payload['value']:
                yield item
            url = response.next_link
        else:
            yield payload
            return
        pages += 1
        if max_pages is not None and pages >= max_pages:
            return
