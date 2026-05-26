"""Generic Microsoft Graph upload-session driver.

Graph's resumable upload protocol is the same regardless of what is
being uploaded (OneDrive items, mail attachments, ...): the caller
creates a session against the relevant endpoint, gets back a
short-lived pre-authorized `uploadUrl`, and then PUTs the bytes to
that URL in sequential chunks.

This module owns only the second half - chunking bytes and PUTting
them to a given `uploadUrl`. It is intentionally drive-agnostic so
mail attachments can reuse it. Session creation lives with each
caller because the create endpoint and body differ per resource.

The chunk PUTs are *unauthenticated*: the `uploadUrl` is already
pre-signed by Graph, and attaching a bearer token can break it. We
therefore use `owa_core.http.request_unauthenticated` (which does not
set `Authorization`) rather than the standard `http.request`. All raw
urllib lives in `owa_core.http` per the suite's architecture contract;
this module is pure protocol orchestration.

Failure handling: a clear failure is raised on the first chunk that
errors. We do not attempt resume-after-failure (querying
`nextExpectedRanges` and replaying) - the simple-but-correct choice.
Transient 429/503 on a single chunk are retried in place honoring
`Retry-After` (handled by `request_unauthenticated`).
"""
import json
import sys

from . import http
from .errors import InternalError

# Graph requires every non-final chunk to be a multiple of 320 KiB.
CHUNK_MULTIPLE = 320 * 1024  # 327680 bytes
# Default ~10 MiB. 10 MiB is already a clean 320 KiB multiple:
# 10 * 1024 * 1024 / 327680 == 32.
DEFAULT_CHUNK_SIZE = 32 * CHUNK_MULTIPLE  # 10 MiB


def _normalize_chunk_size(chunk_size):
    if chunk_size <= 0:
        raise InternalError(f'invalid chunk size: {chunk_size}')
    if chunk_size < CHUNK_MULTIPLE:
        return CHUNK_MULTIPLE
    return (chunk_size // CHUNK_MULTIPLE) * CHUNK_MULTIPLE


def _decode_json(raw):
    if not raw:
        return {}
    try:
        return json.loads(raw.decode('utf-8', errors='replace'))
    except json.JSONDecodeError as exc:
        raise InternalError('upload response was not valid JSON', cause=exc)


def upload_session(
    upload_url,
    content,
    *,
    chunk_size=DEFAULT_CHUNK_SIZE,
    timeout=300,
    retry=3,
    debug=False,
    sleep=None,
    urlopen=None,
):
    """Drive a Graph upload session to completion and return the final item.

    Given a pre-authorized `upload_url` and the full `content` bytes,
    PUT the bytes in sequential chunks (each a 320 KiB multiple except
    the last) and return the parsed driveItem/attachment JSON from the
    final response.

    Chunk PUTs are unauthenticated - `upload_url` is already pre-signed
    by Graph, so no bearer token is attached. The transport is injectable
    via `urlopen` for tests (forwarded to `http.request_unauthenticated`).

    Raises an `OwaError` subclass on failure (InternalError for HTTP/
    protocol errors, NetworkError for transport errors, RateLimitedError
    when a server-requested backoff exceeds the cap).
    """
    chunk_size = _normalize_chunk_size(chunk_size)
    total = len(content)
    if debug:
        print(
            f'DEBUG: upload session {total} bytes in chunks of {chunk_size}',
            file=sys.stderr,
        )

    # Forward only the transport overrides the caller actually set, so
    # http.request_unauthenticated keeps its own stdlib defaults.
    transport = {}
    if sleep is not None:
        transport['sleep'] = sleep
    if urlopen is not None:
        transport['urlopen'] = urlopen

    start = 0
    final = None
    while True:
        end = min(start + chunk_size, total)
        chunk = content[start:end]
        # Content-Range end is inclusive; guard the empty-content case so
        # the range stays non-negative (`bytes 0-0/0`).
        last_index = max(end - 1, 0)
        headers = {
            'Content-Length': str(len(chunk)),
            'Content-Range': f'bytes {start}-{last_index}/{total}',
        }
        if debug:
            print(
                f'DEBUG: PUT chunk {headers["Content-Range"]} ({len(chunk)} bytes)',
                file=sys.stderr,
            )
        response = http.request_unauthenticated(
            'PUT',
            upload_url,
            body=chunk,
            headers=headers,
            timeout=timeout,
            retry=retry,
            debug=debug,
            **transport,
        )
        if end >= total:
            # Final chunk: Graph returns 200/201 with the item JSON.
            if response.status not in (200, 201):
                raise InternalError(
                    f'upload did not complete: final chunk returned '
                    f'HTTP {response.status}',
                )
            final = _decode_json(response.bytes)
            break
        # Intermediate chunk: Graph returns 202 (Accepted).
        if response.status != 202:
            raise InternalError(
                f'unexpected status {response.status} for non-final upload chunk',
            )
        start = end

    if not isinstance(final, dict):
        raise InternalError('upload completed without an item payload')
    return final
