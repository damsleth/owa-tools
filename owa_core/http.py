"""HTTP client over urllib.

Public surface:
    request(method, url, *, token, body=None, headers=None, retry=3, etag=None) -> Response
    paginate(url, *, token, page_size=50, max_pages=None) -> Iterator[dict]
    Response (dataclass)

Behavior:
    - Honors Retry-After on 429.
    - Retries 5xx with capped exponential backoff (1, 2, 4 seconds).
    - Follows @odata.nextLink only via paginate().
    - Maps known auth/HTTP failures into typed errors from owa_core.errors:
        401              -> AuthExpiredError
        403 (scope hint) -> ScopeInsufficientError (else NetworkError)
        404              -> NotFoundError
        409, 412         -> ConflictError
        429 (exhausted)  -> RateLimitedError
        URLError, etc.   -> NetworkError
    - Honors If-Match / If-None-Match via the etag arg.
"""
from __future__ import annotations

import json as _json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator

from .errors import (
    AuthExpiredError,
    ConflictError,
    NetworkError,
    NotFoundError,
    RateLimitedError,
    ScopeInsufficientError,
)


@dataclass
class Response:
    status: int
    headers: dict[str, str]
    bytes: bytes = b""
    json: Any = None
    next_link: str | None = None
    etag: str | None = None
    _raw: dict[str, Any] = field(default_factory=dict)


def _parse_body(raw: bytes, content_type: str) -> Any:
    if not raw:
        return None
    if "json" in content_type.lower():
        try:
            return _json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None
    return None


def _is_scope_error(body: Any) -> bool:
    if not isinstance(body, dict):
        return False
    err = body.get("error") if isinstance(body.get("error"), dict) else body
    code = (err.get("code") or "").lower() if isinstance(err, dict) else ""
    msg = (err.get("message") or "").lower() if isinstance(err, dict) else ""
    return "scope" in code or "insufficient" in code or "scope" in msg or "consent" in msg


def _retry_after(headers: dict[str, str]) -> float:
    raw = headers.get("Retry-After") or headers.get("retry-after")
    if not raw:
        return 0.0
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 0.0


def _do_one(
    method: str,
    url: str,
    *,
    token: str,
    body: Any | None,
    headers: dict[str, str] | None,
    etag: str | None,
) -> Response:
    hdrs: dict[str, str] = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": "owa-tools/0.0",
    }
    if headers:
        hdrs.update(headers)
    if etag:
        if method.upper() in ("GET", "HEAD"):
            hdrs.setdefault("If-None-Match", etag)
        else:
            hdrs.setdefault("If-Match", etag)
    data: bytes | None = None
    if body is not None:
        if isinstance(body, (bytes, bytearray)):
            data = bytes(body)
        else:
            data = _json.dumps(body, ensure_ascii=False).encode("utf-8")
            hdrs.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, method=method.upper(), headers=hdrs)
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read()
            resp_headers = {k: v for k, v in resp.headers.items()}
            ctype = resp_headers.get("Content-Type", "")
            parsed = _parse_body(raw, ctype)
            next_link = parsed.get("@odata.nextLink") if isinstance(parsed, dict) else None
            return Response(
                status=resp.status,
                headers=resp_headers,
                bytes=raw,
                json=parsed,
                next_link=next_link,
                etag=resp_headers.get("ETag"),
            )
    except urllib.error.HTTPError as e:
        raw = e.read() if hasattr(e, "read") else b""
        resp_headers = {k: v for k, v in (e.headers.items() if e.headers else [])}
        parsed = _parse_body(raw, resp_headers.get("Content-Type", ""))
        return Response(
            status=e.code,
            headers=resp_headers,
            bytes=raw,
            json=parsed,
            next_link=None,
            etag=resp_headers.get("ETag"),
        )
    except urllib.error.URLError as e:
        raise NetworkError(f"network error: {e.reason}") from e
    except OSError as e:
        raise NetworkError(f"network error: {e}") from e


def _map_failure(resp: Response) -> Exception | None:
    s = resp.status
    if 200 <= s < 300:
        return None
    if s == 401:
        return AuthExpiredError(
            "access token rejected (401)",
            hint="re-seed with `owa-piggy setup` or refresh the profile",
        )
    if s == 403:
        if _is_scope_error(resp.json):
            return ScopeInsufficientError(
                "insufficient scope for this resource (403)",
                hint="check the audience and scopes granted to owa-piggy",
            )
        return NetworkError(f"forbidden (403)")
    if s == 404:
        return NotFoundError("not found (404)")
    if s in (409, 412):
        return ConflictError(f"conflict ({s})")
    return None


def request(
    method: str,
    url: str,
    *,
    token: str,
    body: Any | None = None,
    headers: dict[str, str] | None = None,
    retry: int = 3,
    etag: str | None = None,
    _sleep: Callable[[float], None] = time.sleep,
) -> Response:
    """One HTTP call with retry on 429/5xx.

    Retries are capped at ``retry`` total attempts; non-retryable
    statuses surface immediately.
    """
    attempts = max(1, retry)
    backoff = 1.0
    last: Response | None = None
    for i in range(attempts):
        resp = _do_one(method, url, token=token, body=body, headers=headers, etag=etag)
        last = resp
        if resp.status < 400:
            return resp
        if resp.status == 429:
            wait = _retry_after(resp.headers) or backoff
            if i + 1 < attempts:
                _sleep(wait)
                backoff = min(backoff * 2, 8.0)
                continue
            raise RateLimitedError(
                "rate limited (429)",
                hint=f"retry after {wait:.0f}s",
            )
        if 500 <= resp.status < 600:
            if i + 1 < attempts:
                _sleep(backoff)
                backoff = min(backoff * 2, 8.0)
                continue
            raise NetworkError(f"server error ({resp.status})")
        mapped = _map_failure(resp)
        if mapped is not None:
            raise mapped
        return resp
    assert last is not None
    return last


def paginate(
    url: str,
    *,
    token: str,
    page_size: int = 50,
    max_pages: int | None = None,
    headers: dict[str, str] | None = None,
) -> Iterator[dict]:
    """Walk @odata.nextLink chains, yielding individual items.

    The first request appends ``$top=page_size`` if no query string is
    present. Subsequent requests use the server-provided nextLink as-is.
    """
    next_url: str | None = url
    if "?" not in url and page_size:
        next_url = f"{url}?$top={page_size}"
    pages = 0
    while next_url:
        resp = request("GET", next_url, token=token, headers=headers)
        body = resp.json or {}
        items = body.get("value") if isinstance(body, dict) else None
        if isinstance(items, list):
            for item in items:
                yield item
        next_url = resp.next_link
        pages += 1
        if max_pages is not None and pages >= max_pages:
            return
