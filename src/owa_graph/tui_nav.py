"""Navigation engine for the owa-graph interactive explorer (TUI).

This module is the correctness-critical, curses-*free* core: it knows how
to fetch a page safely, classify whatever came back, turn it into a list of
drillable rows, follow links across the suite's many audiences, and page
through the three continuation shapes the suite actually emits. It never
touches curses, never prints, and never raises out of the fetch path — those
are hard requirements of the explorer's curses-safe boundary (see the plan's
"Cross-cutting invariant").

Audience tiers (drive per-audience behaviour):
  A self-describing OData/discovery  — graph, outlook(365), azure, powerbi
  B REST collections (response-driven) — flow, manage, substrate, devops
  C opaque internal Teams APIs        — teams, ic3, csa, presence, uis
  D data-plane, not browseable        — keyvault, storage, sql
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from owa_core import http as _http
from owa_core.errors import (
    AuthExpiredError,
    NotFoundError,
    OwaError,
    RateLimitedError,
    ScopeInsufficientError,
)
from owa_core.secrets import redact

from .paths import all_paths
from .scopes import required_scopes

# ---------------------------------------------------------------------------
# Limits (keep the list bounded so a huge collection can't wedge the redraw)
# ---------------------------------------------------------------------------

MAX_ROWS = 500   # collection items rendered per page
MAX_KEYS = 100   # object keys rendered for a single resource

# Audiences whose pagination follows OData `@odata.nextLink` (the default).
_ODATA_AUDIENCES = frozenset({
    'graph', 'outlook', 'outlook365', 'powerbi', 'flow', 'manage', 'substrate',
})
# Azure Resource Manager family: a *bare* top-level `nextLink`, no `@odata.`.
_ARM_AUDIENCES = frozenset({'azure', 'keyvault', 'storage', 'sql'})
# devops carries its cursor in the `x-ms-continuationtoken` *response header*.

# Link fields we never offer as drill targets: pure metadata, not navigation.
_LINK_DENY = frozenset({
    '@odata.context', '@odata.editlink', 'editlink', '@odata.type', 'type',
    'metadata', 'etag', '@odata.etag', '@odata.count', 'count', '@odata.id',
})

# Human-readable label fields, best-first.
_LABEL_FIELDS = (
    'displayName', 'name', 'subject', 'title', 'givenName',
    'userPrincipalName', 'mail', 'id',
)

_HTTP_RE = re.compile(r'^https?://', re.IGNORECASE)
_GUID_RE = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
    re.IGNORECASE,
)

# Map each fetch-failure exception to a stable status kind. Anything not
# listed (NetworkError, InternalError, ConflictError, …) becomes 'error'.
_STATUS_BY_ERROR = (
    (AuthExpiredError, 'auth'),
    (ScopeInsufficientError, 'scope'),
    (NotFoundError, 'notfound'),
    (RateLimitedError, 'ratelimit'),
)


# ---------------------------------------------------------------------------
# Result / row containers
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FetchResult:
    """One successful HTTP response. Carries headers because devops
    pagination reads its cursor from a response *header*, not the body."""

    status: int
    headers: dict
    body: bytes


@dataclass(frozen=True)
class Row:
    """One rendered list row. `target` is the drill string consumed by
    :func:`next_path`; `drillable` False means Enter is a no-op."""

    label: str
    target: str | None
    drillable: bool
    dim: bool = False


# ---------------------------------------------------------------------------
# Curses-safe fetch
# ---------------------------------------------------------------------------

def _tui_get(url, token, *, debug=False):
    """GET `url` and never raise or print.

    Returns ``('ok', FetchResult)`` on success, else ``(status_kind, msg)``
    where ``status_kind`` is one of auth/scope/notfound/ratelimit/error and
    ``msg`` is a redacted, human-safe string. Always fetches ``raw=True`` so
    JSON decoding can't raise here — :func:`classify_response` decodes itself.
    """
    try:
        resp = _http.request('GET', url, token=token, raw=True, debug=debug)
    except OwaError as error:
        for etype, kind in _STATUS_BY_ERROR:
            if isinstance(error, etype):
                return (kind, redact(error.message))
        return ('error', redact(error.message))
    return (
        'ok',
        FetchResult(
            status=resp.status,
            headers=dict(resp.headers or {}),
            body=resp.bytes or b'',
        ),
    )


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def classify_response(result):
    """Decode a :class:`FetchResult` body and label its shape.

    Kinds: ``collection`` (has a list, paginatable), ``object`` (a single
    resource), ``scalar`` (a bare JSON value), ``opaque`` (body wasn't JSON —
    the only way this kind is reachable, since the normal HTTP layer raises on
    non-JSON and discards the bytes). For ``opaque`` the payload is the raw
    bytes; otherwise the parsed JSON.
    """
    body = result.body or b''
    if not body:
        return ('object', {})
    try:
        payload = json.loads(body.decode('utf-8', errors='replace'))
    except json.JSONDecodeError:
        return ('opaque', body)
    if isinstance(payload, dict):
        if isinstance(payload.get('value'), list):
            return ('collection', payload)
        return ('object', payload)
    if isinstance(payload, list):
        return ('collection', {'value': payload})
    return ('scalar', payload)


# ---------------------------------------------------------------------------
# Row building
# ---------------------------------------------------------------------------

def _row_label(item):
    if isinstance(item, dict):
        for field in _LABEL_FIELDS:
            value = item.get(field)
            if isinstance(value, str) and value:
                return value
        for value in item.values():
            if isinstance(value, str) and value:
                return value
        return '{…}'
    return str(item)


def _drill_target(item):
    """The drill string for a collection item, or None if it can't be
    navigated. Prefers an explicit ``@odata.id`` (often a full URL), then a
    bare ``id`` (a GUID to append, or an ARM ``/subscriptions/…`` path)."""
    if not isinstance(item, dict):
        return None
    for key in ('@odata.id', 'id'):
        value = item.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _is_nav_key(key):
    return (
        key.endswith('@odata.navigationLink')
        or key.endswith('@odata.associationLink')
        or key == '@odata.nextLink'
        or key == 'nextLink'
    )


def _same_host(url, host):
    try:
        return urlsplit(url).netloc.lower() == (host or '').lower()
    except Exception:
        return False


def _preview(value, limit=60):
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False)
    else:
        text = str(value)
    text = text.replace('\n', ' ')
    return text if len(text) <= limit else text[: limit - 1] + '…'


def _object_target(key, value, host):
    """Resolve a (key, value) of a single resource to a drill target.

    A navigation/association-link field is drillable when its value is a
    same-host absolute URL or a relative reference; a cross-host absolute URL
    (CDN/photo/portal links) is detail-only and returns no target.
    """
    if not (_is_nav_key(key) and isinstance(value, str) and value):
        return None
    if _HTTP_RE.match(value):
        return value if _same_host(value, host) else None
    return value


def build_rows(kind, payload, *, host=None):
    """Turn a classified response into a bounded list of :class:`Row`.

    `host` is the netloc of the current request, used to keep cross-host link
    values out of the drillable set.
    """
    if kind == 'opaque':
        return [Row('(binary / non-JSON response — y to yank URL)', None, False)]

    if kind == 'scalar':
        return [Row(_preview(payload, limit=200), None, False)]

    if kind == 'collection':
        values = payload.get('value') if isinstance(payload, dict) else payload
        if not isinstance(values, list):
            values = []
        if not values:
            return [Row('(no items)', None, False)]
        rows = []
        for item in values[:MAX_ROWS]:
            target = _drill_target(item)
            rows.append(Row(_row_label(item), target, target is not None))
        extra = len(values) - MAX_ROWS
        if extra > 0:
            rows.append(Row(f'… {extra} more (n to page)', None, False, dim=True))
        return rows

    # object: one row per key, navigation-link fields drillable.
    rows = []
    keys = list(payload.keys()) if isinstance(payload, dict) else []
    for key in keys[:MAX_KEYS]:
        if key.lower() in _LINK_DENY:
            continue
        value = payload[key]
        target = _object_target(key, value, host)
        if target is not None:
            rows.append(Row(f'{key} →', target, True))
        else:
            rows.append(Row(f'{key}: {_preview(value)}', None, False))
    extra = len(keys) - MAX_KEYS
    if extra > 0:
        rows.append(Row(f'… {extra} more keys', None, False, dim=True))
    return rows


# ---------------------------------------------------------------------------
# Path navigation
# ---------------------------------------------------------------------------

def next_path(current_path, target):
    """Resolve a drill `target` against `current_path` (3 id-shapes):

    - absolute URL (``https://…``)  → navigate by the full URL verbatim
    - absolute path (``/subscriptions/…``, ARM ids) → *replace* the path
    - relative segment (``messages``, a GUID) → *append* to the current path
    """
    if not isinstance(target, str) or not target:
        return current_path
    if _HTTP_RE.match(target):
        return target
    if target.startswith('/'):
        return target
    cur = (current_path or '').strip('/')
    return f'{cur}/{target}' if cur else target


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------

def _header_get(headers, name):
    """Case-insensitive header lookup (``_headers_dict`` keeps server casing,
    so devops' ``X-MS-ContinuationToken`` would miss a plain ``.get``)."""
    name = name.lower()
    for key, value in (headers or {}).items():
        if key.lower() == name:
            return value
    return None


def _continuation_shape(audience):
    if audience in _ARM_AUDIENCES:
        return 'arm'
    if audience == 'devops':
        return 'devops'
    return 'odata'


def _next_cursor(audience, url, payload, headers):
    shape = _continuation_shape(audience)
    if shape == 'odata':
        return payload.get('@odata.nextLink') if isinstance(payload, dict) else None
    if shape == 'arm':
        return payload.get('nextLink') if isinstance(payload, dict) else None
    # devops: continuation token lives in a response header, re-applied as a query arg.
    token = _header_get(headers, 'x-ms-continuationtoken')
    if token:
        sep = '&' if '?' in url else '?'
        return f'{url}{sep}continuationToken={token}'
    return None


def _fetch_page(audience, url, token, *, debug=False):
    """Fetch one page and resolve the per-audience continuation cursor.

    Returns ``(kind, payload, next_cursor)``. On a fetch failure ``kind`` is
    the :func:`_tui_get` status kind (auth/scope/notfound/ratelimit/error),
    ``payload`` the redacted message and ``next_cursor`` None. On success
    ``kind`` is a :func:`classify_response` kind (collection/object/scalar/
    opaque) — the two kind-sets are disjoint, so callers can switch on it.
    """
    status_kind, result = _tui_get(url, token, debug=debug)
    if status_kind != 'ok':
        return (status_kind, result, None)
    kind, payload = classify_response(result)
    body = payload if isinstance(payload, dict) else {}
    cursor = _next_cursor(audience, url, body, result.headers)
    return (kind, payload, cursor)


# ---------------------------------------------------------------------------
# Graph manifest overlay (prefix index + scope hints) — graph audience only
# ---------------------------------------------------------------------------

def _split(path):
    body = path.split('?', 1)[0].split('#', 1)[0].strip('/')
    return [seg for seg in body.split('/') if seg]


def _is_template(seg):
    return seg.startswith('{') and seg.endswith('}')


def _looks_like_id(seg):
    return bool(
        _GUID_RE.match(seg)
        or seg.isdigit()
        or '@' in seg
        or len(seg) > 30
    )


def build_prefix_index(endpoint='v1.0'):
    """Map each path's all-but-last prefix to its direct child segments.

    Key is the normalized parent path (``''`` for top-level); values are the
    last segments verbatim, including ``{var}`` templates. So ``/users`` and
    ``/users/{id}`` register ``users`` under ``''`` and ``{id}`` under
    ``users`` respectively — a child only appears under its *immediate*
    parent, never a grandparent. Returns ``{}`` when the manifest is missing.
    """
    index: dict[str, list[str]] = {}
    for path in all_paths(endpoint):
        segs = _split(path)
        if not segs:
            continue
        prefix = '/'.join(segs[:-1])
        last = segs[-1]
        children = index.setdefault(prefix, [])
        if last not in children:
            children.append(last)
    return index


def _to_template(path, index):
    """Normalize a concrete path to its manifest template form by walking it
    segment-by-segment: a segment kept verbatim if it's a known child, else
    folded to a ``{var}`` sibling when it looks like an id."""
    chosen: list[str] = []
    prefix = ''
    for seg in _split(path):
        children = index.get(prefix, [])
        if seg in children:
            keep = seg
        elif _looks_like_id(seg):
            keep = next((c for c in children if _is_template(c)), seg)
        else:
            keep = seg
        chosen.append(keep)
        prefix = '/'.join(chosen)
    return prefix


def completions_for(path, index):
    """Direct child segments of `path` per the prefix index, after template
    normalization. ``[]`` for non-graph audiences (``index is None``)."""
    if not index:
        return []
    return list(index.get(_to_template(path, index), []))


def scope_hint(path, token_scopes, *, verb='GET'):
    """Return ``(required, missing)`` delegated scopes for a graph path.

    Graph-only: the manifest only describes Graph. `missing` is the subset of
    required scopes absent from the token — an advisory hint, never a block.
    """
    required = required_scopes(verb, path)
    missing = [scope for scope in required if scope not in token_scopes]
    return (required, missing)
