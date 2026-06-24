"""Azure DevOps REST helper for owa-ado.

Differences from the Graph helper (owa_drive.api):
- every request carries an `api-version` query parameter (DevOps refuses
  requests without one and the wire shape is versioned);
- list endpoints return ``{"count": N, "value": [...]}`` rather than an
  ``@odata.nextLink`` envelope, and page via the `x-ms-continuationtoken`
  response header echoed back as a `continuationToken` query param;
- work-item create/update use the JSON Patch media type
  (`application/json-patch+json`) with a list body.

Errors are mapped to the shared OwaError taxonomy (owa_core.errors).
All OwaError subclasses propagate to the caller; the mode wrapper in
cli.py maps them to the 0/2/10-20 exit taxonomy.
"""
import sys
from urllib.parse import quote, urlencode

from owa_core import http

DEFAULT_API_VERSION = '7.1'
CONTINUATION_HEADER = 'x-ms-continuationtoken'


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
    # '%' is safe so callers that pre-encode a free-text segment (e.g. a repo
    # name with a '/') aren't double-encoded here (%2F -> %252F).
    path = quote(endpoint.lstrip('/'), safe="/$:%")
    url = f'{base}/{path}'
    params = {k: v for k, v in (query or {}).items() if v is not None}
    if api_version is not None:
        params['api-version'] = api_version
    if params:
        url = f'{url}?{urlencode(params)}'
    return url


def ado_request(method, base, endpoint, token, *, body=None, query=None,
                api_version=DEFAULT_API_VERSION, extra_headers=None, debug=False):
    """One DevOps REST call. Returns decoded JSON or raises OwaError."""
    url = build_url(base, endpoint, query=query, api_version=api_version)
    headers = dict(extra_headers or {})
    return http.request(
        method, url, token=token, body=body, headers=headers, debug=debug,
    ).json


def ado_paginate(base, endpoint, token, *, query=None,
                 api_version=DEFAULT_API_VERSION, max_items=None, debug=False):
    """Collect `value` items across continuation-token pages.

    DevOps signals "more results" with the `x-ms-continuationtoken`
    response header rather than a next-link URL; echo it back as the
    `continuationToken` query param to fetch the next page. Raises
    OwaError on any HTTP failure; returns the accumulated list otherwise.
    """
    items = []
    cont = None
    base_query = dict(query or {})
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
