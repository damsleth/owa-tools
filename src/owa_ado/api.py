"""Azure DevOps REST helper for owa-ado.

Differences from the Graph helper (owa_drive.api):
- every request carries an `api-version` query parameter (DevOps refuses
  requests without one and the wire shape is versioned);
- list endpoints return ``{"count": N, "value": [...]}`` rather than an
  ``@odata.nextLink`` envelope, and page via the `x-ms-continuationtoken`
  response header echoed back as a `continuationToken` query param;
- work-item create/update use the JSON Patch media type
  (`application/json-patch+json`) with a list body.

Recoverable errors are mapped to None (and printed) exactly as owa_drive
does, so callers branch on `payload is None`. Auth/scope errors re-raise
so the shared mode wrapper can map them to the 0/2/10-20 exit taxonomy.
"""
import sys
from urllib.parse import quote, urlencode

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

DEFAULT_API_VERSION = '7.1'
CONTINUATION_HEADER = 'x-ms-continuationtoken'


def _handle_owa_error(error):
    if isinstance(error, (AuthExpiredError, ScopeInsufficientError)):
        raise error
    if isinstance(error, (ConflictError, InternalError, NetworkError,
                          NotFoundError, RateLimitedError)):
        emit_error(error)
        return None
    if isinstance(error, OwaError):
        emit_error(error)
        return None
    raise error


def build_url(base, endpoint, *, query=None, api_version=DEFAULT_API_VERSION):
    """Join base + endpoint and attach query params + api-version.

    `query` values that are None are dropped, so callers can pass optional
    filters inline without pre-filtering. `api_version=None` omits the
    parameter (a few preview endpoints pin their own).
    """
    # Percent-encode the path: team/project/repo names legitimately contain
    # spaces (e.g. "NOCOS Team") and stdlib's http client rejects a raw space
    # with InvalidURL. Keep '/' (segment separators), '$' (the `$Type` route
    # in work-item create), and ':' safe so those structural chars survive.
    path = quote(endpoint.lstrip('/'), safe="/$:")
    url = f'{base}/{path}'
    params = {k: v for k, v in (query or {}).items() if v is not None}
    if api_version is not None:
        params['api-version'] = api_version
    if params:
        url = f'{url}?{urlencode(params)}'
    return url


def ado_request(method, base, endpoint, token, *, body=None, query=None,
                api_version=DEFAULT_API_VERSION, extra_headers=None, debug=False):
    """One DevOps REST call. Returns decoded JSON, or None on a recoverable
    error (auth/scope re-raise)."""
    url = build_url(base, endpoint, query=query, api_version=api_version)
    headers = dict(extra_headers or {})
    try:
        return http.request(
            method, url, token=token, body=body, headers=headers, debug=debug,
        ).json
    except OwaError as error:
        return _handle_owa_error(error)


def ado_paginate(base, endpoint, token, *, query=None,
                 api_version=DEFAULT_API_VERSION, max_items=None, debug=False):
    """Collect `value` items across continuation-token pages.

    DevOps signals "more results" with the `x-ms-continuationtoken`
    response header rather than a next-link URL; echo it back as the
    `continuationToken` query param to fetch the next page. Returns the
    accumulated list, or None on a recoverable error.
    """
    items = []
    cont = None
    base_query = dict(query or {})
    try:
        while True:
            page_query = dict(base_query)
            if cont:
                page_query['continuationToken'] = cont
            url = build_url(base, endpoint, query=page_query, api_version=api_version)
            response = http.request('GET', url, token=token, debug=debug)
            payload = response.json
            if not isinstance(payload, dict) or not isinstance(payload.get('value'), list):
                # Not a list envelope - hand the single payload back so the
                # caller still gets something usable.
                return [payload] if payload is not None else []
            items.extend(payload['value'])
            cont = (response.headers.get(CONTINUATION_HEADER)
                    or response.headers.get(CONTINUATION_HEADER.title()))
            if not cont:
                break
            if max_items is not None and len(items) >= max_items:
                break
    except OwaError as error:
        return _handle_owa_error(error)
    return items[:max_items] if max_items is not None else items


def json_patch(method, base, endpoint, token, *, operations, query=None,
               api_version=DEFAULT_API_VERSION, debug=False):
    """POST/PATCH a JSON Patch document (work-item create/update).

    `operations` is a list of {op, path, value} dicts. DevOps requires the
    `application/json-patch+json` media type here; passing it explicitly
    keeps owa_core.http from defaulting to `application/json`.
    """
    if debug:
        print(f'DEBUG: {method} json-patch ({len(operations)} ops)', file=sys.stderr)
    return ado_request(
        method, base, endpoint, token,
        body=operations, query=query, api_version=api_version,
        extra_headers={'Content-Type': 'application/json-patch+json'},
        debug=debug,
    )
