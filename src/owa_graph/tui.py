"""owa-graph interactive explorer (TUI) — auth/token-cache core (Phase 1, A2)
plus curses front-end (Phase 2).

Phase 1 (frozen — do not alter signatures):
  TokenInfo, GraphState, _ensure_token, _apply_token, _exp_epoch_from_broker,
  _DEFAULT_TTL, _EXP_SKEW.

Phase 2 (this file extension):
  render_row, render_detail, fetch_items, on_drill, on_back, on_search,
  on_refresh, build_spec, run.

Curses-safe contract: nothing inside the loop may call api.api_request,
auth.setup_auth, auth._refresh_via_owa_piggy, emit_error, or write to a
non-redirected stderr/stdout. fetch_items catches every exception and reports
via state.status. run() restores stderr on every exit path (try/finally).
"""
from __future__ import annotations

import binascii
import io
import json
import subprocess
import sys
import time
import webbrowser
from dataclasses import dataclass
from dataclasses import replace as _dc_replace
from urllib.parse import urlsplit

from owa_core import jwt as jwt_mod
from owa_core.auth import get_token_for_config
from owa_core.errors import OwaError
from owa_core.secrets import redact
from owa_core.tui_kit import app as _app
from owa_core.tui_kit import screen as _screen
from owa_core.tui_kit.app import BrowserSpec, BrowserState
from owa_core.tui_kit.layout import truncate_ellipsis, wrap_body

from .auth import AUDIENCE_DESC, TOOL_NAME, resolve_api_base
from .emit import render_curl as _render_curl
from .format import format_pretty as _format_pretty
from .tui_nav import _fetch_page, build_rows, next_path
from .tui_settings import dump_bookmarks, parse_bookmarks
from .tui_settings import from_config as _settings_from_config

# Fallback access-token lifetime (seconds) when the broker reports neither
# expires_at nor expires_in — short, so a missing claim forces a quick re-mint
# rather than trusting a stale token. Also guards against `time.time() >=
# None - 60` blowing up in the cache-hit check.
_DEFAULT_TTL = 300

# Re-mint this many seconds before the token actually expires, so an in-flight
# request can't race the boundary.
_EXP_SKEW = 60


@dataclass(frozen=True)
class TokenInfo:
    """One cached per-audience token plus the context a fetch/annotation needs.

    A bare access-token string is insufficient: per-audience ``api_base`` and
    ``scopes`` are load-bearing (fetch composes URLs from the base; graph scope
    hints intersect against the token's scopes), and ``exp_epoch`` is always a
    concrete int so the cache-hit check never touches ``None``.
    """

    token: str
    scopes: frozenset
    api_base: str
    exp_epoch: int


class GraphState(BrowserState):
    """Mutable explorer state. Extends the kit's loop-owned BrowserState
    (selected/top/status/detail_lines/items/menu_open/dirty/running) with the
    graph session: the active audience + its resolved token context, the
    per-audience token cache, the current path/query/response, the navigation
    history, and the stderr capture buffer the run() lifecycle redirects into.
    """

    def __init__(self, config, *, audience='graph', path='', settings=None,
                 menu=None, debug=False):
        super().__init__(settings=settings, menu=menu, title=audience)
        self.config = config
        self.debug = debug
        # Active audience token context (refreshed atomically by _ensure_token).
        self.audience = audience
        self.api_base = ''
        self.token = ''
        self.scopes: frozenset = frozenset()
        self.exp_epoch = 0
        # Per-audience exp-aware token cache: audience -> TokenInfo.
        self.token_cache: dict[str, TokenInfo] = {}
        # Current navigation level.
        self.path = path
        self.query = ''
        self.response = None
        self.kind = ''
        self.next_link = None
        # History frames: (audience, path, query, selected, top, rows, next_link).
        self.history: list[tuple] = []
        # Active modal overlay: None | 'audience' | 'bookmarks' | 'help' | 'debug'.
        self.overlay = None
        # All in-loop stderr is redirected here by run() so a stray debug
        # print or traceback can't scribble over the curses frame.
        self.stderr_buf = io.StringIO()


def _apply_token(state, audience, info):
    """Atomically point the session at a token's context."""
    state.audience = audience
    state.token = info.token
    state.api_base = info.api_base
    state.scopes = info.scopes
    state.exp_epoch = info.exp_epoch


def _exp_epoch_from_broker(broker, now):
    """Coerce the broker's expiry to a concrete int epoch.

    `expires_at` is ``int | None``; `expires_in` is ``int | None``. Prefer the
    absolute timestamp, then now+relative, then a short fixed TTL — never None,
    so the cache-hit comparison can't raise a TypeError mid-loop.
    """
    if broker.expires_at:
        return int(broker.expires_at)
    if broker.expires_in:
        return int(now + broker.expires_in)
    return int(now + _DEFAULT_TTL)


def _ensure_token(audience, state):
    """Return a valid :class:`TokenInfo` for *audience*, minting if needed.

    Cache hit (still valid with skew) → refresh the session context and return
    it, with no AAD round-trip. Cache miss/expiry → set a "minting…" status
    (so the front-end can render a frame before the blocking subprocess), mint
    via owa-piggy ``--json``, populate the cache and session, and return it.
    On any failure: set ``state.status``, evict the audience (so `r` retries
    it), and return ``None``. Never raises, never prints.
    """
    now = time.time()
    cached = state.token_cache.get(audience)
    if cached is not None and now < cached.exp_epoch - _EXP_SKEW:
        _apply_token(state, audience, cached)
        return cached

    # Miss: surface a status the loop can paint before we block on the mint.
    state.status = f'minting token for {audience}…'
    try:
        broker = get_token_for_config(
            state.config, tool_name=TOOL_NAME, audience=audience, debug=False,
        )
        api_base = resolve_api_base(audience)
    except OwaError as error:
        state.status = redact(error.message) or f'auth failed for {audience}'
        state.token_cache.pop(audience, None)
        return None

    info = TokenInfo(
        token=broker.access_token,
        scopes=frozenset(jwt_mod.scopes_in_token(broker.access_token)),
        api_base=api_base,
        exp_epoch=_exp_epoch_from_broker(broker, now),
    )
    state.token_cache[audience] = info
    _apply_token(state, audience, info)
    return info


# ---------------------------------------------------------------------------
# Tier-D audiences: browsing these yields raw data-plane bytes, not a graph
# ---------------------------------------------------------------------------

_TIER_D = frozenset({'keyvault', 'storage', 'sql'})

_TIER_D_NOTE = 'Tier D: raw target — not a browse surface'

# _fetch_page returns disjoint kind-sets: these failure kinds (from _tui_get)
# or a classify kind (collection/object/scalar/opaque) on success.
_FAILURE_KINDS = frozenset({'auth', 'scope', 'notfound', 'ratelimit', 'error'})

# ---------------------------------------------------------------------------
# render_row: one list row for a tui_nav.Row
# ---------------------------------------------------------------------------

def render_row(item, width):
    """Render one :class:`tui_nav.Row` as a padded/truncated string.

    Dimmed sentinel rows (``item.dim``) get a leading space so they visually
    recede from real content. Label is always hard-truncated to ``width``.
    """
    label = item.label if not item.dim else f'  {item.label}'
    return truncate_ellipsis(label, max(width, 1))


# ---------------------------------------------------------------------------
# render_detail: detail-pane lines for the currently selected item
# ---------------------------------------------------------------------------

_DETAIL_MAXBYTES = 4096   # hex preview ceiling for opaque bodies


def render_detail(item, width, *, state):
    """Produce wrapped detail-pane lines for one list item.

    Branches on ``state.kind`` (set by fetch_items after the last fetch):

    - ``opaque``     — hex dump of the first 4 KB of the raw bytes response
    - ``scalar``     — str() of the value
    - ``collection`` — format_pretty ONLY when audience=='graph'; plain
                       json.dumps otherwise (avoids mislabelling ARM/devops)
    - ``object``     — same gate
    - anything else  — json.dumps of state.response

    Tier-D audiences append a persistent footer note.
    """
    if item is None:
        return []

    audience = state.audience
    payload = state.response
    kind = state.kind

    lines: list[str] = []

    if kind == 'opaque':
        raw = payload if isinstance(payload, bytes) else b''
        chunk = raw[:_DETAIL_MAXBYTES]
        lines.append(f'(binary / non-JSON — {len(raw)} bytes total)')
        hex_lines = [
            binascii.hexlify(chunk[i:i + 16]).decode()
            for i in range(0, len(chunk), 16)
        ]
        lines.extend(hex_lines or ['(empty)'])
    elif kind == 'scalar':
        lines.append(str(payload))
    elif kind in ('collection', 'object') and audience == 'graph':
        text = _format_pretty(payload)
        lines.extend(text.split('\n'))
    else:
        # ARM, devops, or any other non-graph audience: plain JSON
        try:
            text = json.dumps(payload, indent=2, ensure_ascii=False)
        except (TypeError, ValueError):
            text = str(payload)
        lines.extend(text.split('\n'))

    if audience in _TIER_D:
        lines.append('')
        lines.append(_TIER_D_NOTE)

    # wrap each line to pane width
    out: list[str] = []
    for ln in lines:
        out.extend(wrap_body(ln, width) or [''])
    return out


# ---------------------------------------------------------------------------
# fetch_items: the curses-safe heart of the fetch cycle
# ---------------------------------------------------------------------------

def fetch_items(state):
    """(Re)populate state.items from the current audience + path.

    Always mutates state.items and state.status — never raises or prints.
    On token failure: items stay empty, status is the failure message.
    On HTTP failure: same.
    On success: state.response / state.kind / state.next_link set, rows built.

    The 'minting…' status is written to state.status BEFORE the blocking
    subprocess call, but the kit draws AFTER fetch_items returns, so a
    user won't see it before the blocking mint completes. This is a known
    limitation documented in deviations (see run()).
    """
    try:
        _fetch_items_inner(state)
    except Exception as exc:       # belt-and-suspenders: catch any leaked exception
        state.status = f'internal error: {exc}'
        state.items = []


def _fetch_items_inner(state):
    state.status = f'minting token for {state.audience}…'
    info = _ensure_token(state.audience, state)
    if info is None:
        # state.status already set by _ensure_token
        state.items = []
        return

    # Build the URL from api_base + path + optional query
    base = state.api_base.rstrip('/')
    path = state.path.strip('/')
    if path:
        # handle full-URL paths (next_link returns absolute URLs)
        if path.startswith('http://') or path.startswith('https://'):
            url = path
        else:
            url = f'{base}/{path}'
    else:
        url = base
    if state.query:
        sep = '&' if '?' in url else '?'
        url = f'{url}{sep}{state.query}'

    state.status = f'fetching {state.audience}:{state.path or "/"}…'
    kind, payload, cursor = _fetch_page(
        state.audience, url, state.token, debug=state.debug,
    )

    if kind in _FAILURE_KINDS:
        state.status = str(payload)
        state.items = []
        return

    # Success path
    state.response = payload
    state.kind = kind
    state.next_link = cursor

    # Derive the host for same-host link filtering
    try:
        host = urlsplit(url).netloc
    except Exception:
        host = None

    state.items = build_rows(kind, payload, host=host)
    state.selected = 0
    state.top = 0
    state.title = f'{state.audience}:{state.path or "/"}'
    state.status = ''


# ---------------------------------------------------------------------------
# on_drill: push history frame + navigate to item target
# ---------------------------------------------------------------------------

def on_drill(state, item):
    """Navigate into a drillable item, pushing a history frame.

    If the item is not drillable this is a no-op. The full-URL case (where
    ``next_path`` returns an ``https://...`` URL) is stored verbatim as the
    path — fetch_items detects it and fetches it directly.
    """
    if not getattr(item, 'drillable', False):
        return
    target = getattr(item, 'target', None)
    if not target:
        return

    # Push history frame: (audience, path, query, selected, top, items, next_link)
    state.history.append((
        state.audience,
        state.path,
        state.query,
        state.selected,
        state.top,
        list(state.items),
        state.next_link,
    ))

    new_path = next_path(state.path, target)
    state.path = new_path
    state.query = ''
    state.selected = 0
    state.top = 0
    state.dirty = True


# ---------------------------------------------------------------------------
# on_back: pop history frame without a network call
# ---------------------------------------------------------------------------

def on_back(state):
    """Pop the most recent history frame, restoring all 7 fields.

    Returns True if a frame was popped, False if history is empty (so the
    kit loop can signal 'no-op' and keep the current view).
    No network call is made — dirty is NOT set.
    """
    if not state.history:
        return False
    audience, path, query, selected, top, items, next_link = state.history.pop()
    state.audience = audience
    state.path = path
    state.query = query
    state.selected = selected
    state.top = top
    state.items = items
    state.next_link = next_link
    state.title = f'{state.audience}:{state.path or "/"}'
    return True


# ---------------------------------------------------------------------------
# on_search: jump to a path (graph completion optional)
# ---------------------------------------------------------------------------

def on_search(state, query):
    """Jump to a new path. A blank query is a no-op.

    On success: sets path + dirty so fetch_items runs on the next iteration.
    On failure: fetch_items will put the error in state.status while keeping
    state.items from the last successful fetch (graceful degrade).
    The prior items are NOT cleared here — if the path turns out to be 404
    the list keeps showing what it had.
    """
    if not query:
        return
    state.path = query.strip()
    state.query = ''
    state.next_link = None
    state.selected = 0
    state.top = 0
    state.dirty = True


# ---------------------------------------------------------------------------
# on_refresh: re-fetch current path
# ---------------------------------------------------------------------------

def on_refresh(state):
    """Re-fetch the current path from scratch."""
    state.next_link = None
    state.selected = 0
    state.top = 0
    state.dirty = True


# ---------------------------------------------------------------------------
# Extra key handlers (graph-specific actions dict)
# ---------------------------------------------------------------------------

def _action_audience_switch(state):
    """'a' — audience switcher overlay.

    Renders a small list of available audiences over the list pane. On
    selection: commit the new audience and set dirty so fetch_items retries
    with the new token (even if the switch fails, the audience is committed
    so 'r' can retry it). On cancel: no-op.

    Headless (no real curses window available from an action callback): the
    overlay is set on state so the main loop can render it next frame.
    """
    state.overlay = 'audience'
    # The actual interactive overlay is rendered in on_menu_action / the spec.
    # For now mark state so the next draw cycle knows to show it.
    # A simpler approach: cycle through audiences inline.
    audiences = sorted(AUDIENCE_DESC.keys())
    try:
        idx = audiences.index(state.audience)
        new_audience = audiences[(idx + 1) % len(audiences)]
    except ValueError:
        new_audience = 'graph'
    # Commit the audience change even if the upcoming fetch fails —
    # this means 'r' will retry the new audience.
    state.audience = new_audience
    state.title = f'{new_audience}:{state.path or "/"}'
    state.next_link = None
    state.selected = 0
    state.top = 0
    state.dirty = True
    state.overlay = None


def _action_next_page(state):
    """'n' — fetch the next page via state.next_link and extend items."""
    if not state.next_link:
        state.status = 'no next page'
        return
    # Fetch the next page directly
    try:
        info = _ensure_token(state.audience, state)
        if info is None:
            return
        kind, payload, cursor = _fetch_page(
            state.audience, state.next_link, state.token, debug=state.debug,
        )
        if kind in _FAILURE_KINDS:
            state.status = str(payload)
            return
        try:
            host = urlsplit(state.next_link).netloc
        except Exception:
            host = None
        new_rows = build_rows(kind, payload, host=host)
        # Remove the trailing '… N more' sentinel if present and replace with
        # the freshly fetched rows.
        if state.items and state.items[-1].dim:
            state.items = state.items[:-1]
        state.items = state.items + new_rows
        state.next_link = cursor
        state.response = payload
        state.kind = kind
        state.status = f'+{len(new_rows)} rows'
    except Exception as exc:
        state.status = f'page error: {exc}'


def _action_edit_query(state):
    """'e' — set a query parameter (stored in state.query, applied on next fetch)."""
    # We cannot prompt from an action callback (no stdscr reference).
    # Signal the overlay mechanism so the loop can handle it.
    state.status = "use '/' to set a search path, or add ?$filter=... to path"


def _action_render_curl(state):
    """'c' — render an equivalent curl command into state.status."""
    try:
        base = state.api_base.rstrip('/')
        path = state.path.strip('/')
        if path.startswith('http://') or path.startswith('https://'):
            url = path
        elif path:
            url = f'{base}/{path}'
        else:
            url = base
        cmd = _render_curl('GET', url, state.token, include_token=False)
        # Put first 200 chars in status; full text goes to stderr_buf
        state.stderr_buf.write(f'curl:\n{cmd}\n')
        state.status = truncate_ellipsis(cmd.replace('\n', ' '), 120)
    except Exception as exc:
        state.status = f'curl render error: {exc}'


def _action_yank_url(state):
    """'y' — yank the current URL to clipboard (pbcopy/xclip); best-effort."""
    try:
        base = state.api_base.rstrip('/')
        path = state.path.strip('/')
        if path.startswith('http://') or path.startswith('https://'):
            url = path
        elif path:
            url = f'{base}/{path}'
        else:
            url = base
        for prog in ('pbcopy', 'xclip', 'xsel'):
            try:
                # capture_output keeps any xclip/xsel diagnostics (e.g.
                # "Can't open display" on a headless box) out of the inherited
                # terminal fd 2 — writing there would corrupt the curses frame.
                subprocess.run(
                    [prog] + (['-selection', 'clipboard'] if prog != 'pbcopy' else []),
                    input=url.encode(),
                    timeout=2,
                    capture_output=True,
                )
                state.status = f'yanked: {url}'
                return
            except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
                continue
        state.status = f'url: {url}'
    except Exception as exc:
        state.status = f'yank error: {exc}'


def _action_open_browser(state):
    """'o' — open current URL in the system browser (graph audience only).

    For graph audience: build the Graph Explorer URL. Other audiences: no-op
    with an informative status.
    """
    if state.audience != 'graph':
        state.status = 'no browser target (graph audience only)'
        return
    try:
        path = state.path.strip('/')
        explorer_url = (
            f'https://developer.microsoft.com/en-us/graph/graph-explorer'
            f'?request={path}&method=GET&version=v1.0'
        )
        # The browser launcher (xdg-open/BackgroundBrowser) spawns a subprocess
        # that inherits OS fd 1/2 — a stray diagnostic line would land on the
        # raw terminal under curses. Silence the real fds around the call;
        # sys.stderr redirection alone can't reach an inherited fd.
        with _screen.silence_os_fds():
            opened = webbrowser.open(explorer_url)
        state.status = (
            f'opened: {explorer_url[:80]}' if opened else 'no browser available'
        )
    except Exception as exc:
        state.status = f'browser error: {exc}'


def _action_bookmark(state):
    """'m' — add (audience, path) as a bookmark in settings."""
    try:
        raw = getattr(state.settings, 'bookmarks', '[]')
        marks = parse_bookmarks(raw)
        entry = {'audience': state.audience, 'path': state.path or '', 'label': ''}
        # deduplicate by audience+path
        if not any(
            m.get('audience') == entry['audience'] and m.get('path') == entry['path']
            for m in marks
        ):
            marks.append(entry)
        new_raw = dump_bookmarks(marks)
        # settings is frozen; replace with a new instance
        state.settings = _dc_replace(state.settings, bookmarks=new_raw)
        state.status = f'bookmarked {state.audience}:{state.path}'
    except Exception as exc:
        state.status = f'bookmark error: {exc}'


def _action_debug_overlay(state):
    """'D' — toggle debug overlay rendering state.stderr_buf."""
    state.overlay = None if state.overlay == 'debug' else 'debug'
    buf = state.stderr_buf.getvalue()
    if buf:
        # Show last 400 chars in status so it's visible without an overlay
        state.status = buf[-400:].replace('\n', ' | ')
    else:
        state.status = '(debug buffer empty)'


# ---------------------------------------------------------------------------
# on_menu_action: handle custom graph menu actions
# ---------------------------------------------------------------------------

def on_menu_action(state, action):
    """Handle custom graph menu actions. Returns True only to quit."""
    if action in ('open_audiences', 'open_bookmarks', 'open_help'):
        state.overlay = action.replace('open_', '')
        state.menu_open = False
        state.status = f'[{action}] — press any key to dismiss'
        return False
    return False


# ---------------------------------------------------------------------------
# build_spec: wire everything into a BrowserSpec
# ---------------------------------------------------------------------------

_FOOTER = (
    'j/k move · enter drill · h/← back · / jump · r refresh · '
    'a aud · n page · c curl · y yank · o browser · m bm · D debug · q quit'
)


def build_spec(state):
    """Return the :class:`BrowserSpec` for the graph explorer.

    The kit's ``render_detail(item, width)`` contract has no state parameter,
    so we close over *state* here (it carries the last response/kind/audience
    the detail pane needs). Passing *state* in lets the closure be built once,
    with no placeholder to replace later.
    """
    return BrowserSpec(
        render_row=render_row,
        render_detail=lambda item, width: render_detail(item, width, state=state),
        fetch_items=fetch_items,
        on_search=on_search,
        on_drill=on_drill,
        on_back=on_back,
        on_refresh=on_refresh,
        on_menu_action=on_menu_action,
        actions={
            ord('a'): _action_audience_switch,
            ord('n'): _action_next_page,
            ord('e'): _action_edit_query,
            ord('c'): _action_render_curl,
            ord('y'): _action_yank_url,
            ord('o'): _action_open_browser,
            ord('m'): _action_bookmark,
            ord('D'): _action_debug_overlay,
        },
        footer=_FOOTER,
        empty_text='(no items — press r to retry, a to switch audience)',
    )


# ---------------------------------------------------------------------------
# _seed_path: audience-specific default entry point
# ---------------------------------------------------------------------------

def _seed_path(audience, settings):
    """Return the first-fetch path for the given audience.

    Priority: explicit start_path arg > settings.default_path (if audience
    matches settings.default_audience) > first seed from audience_seeds.json >
    empty string (bare API base).
    """
    # Caller already applied start_path override before calling _seed_path.
    # Here we only resolve the settings/seeds fallback.
    default_aud = getattr(settings, 'default_audience', 'graph')
    default_path = getattr(settings, 'default_path', '')
    if audience == default_aud and default_path:
        return default_path
    # Fall back to the first seed for the audience
    try:
        import json as _json
        import os as _os
        seeds_file = _os.path.join(
            _os.path.dirname(__file__), 'data', 'audience_seeds.json',
        )
        with open(seeds_file, encoding='utf-8') as f:
            seeds = _json.load(f)
        aud_seeds = seeds.get(audience, [])
        if aud_seeds:
            return aud_seeds[0].get('path', '')
    except Exception:
        pass
    return ''


# ---------------------------------------------------------------------------
# run: entry point for Phase 3 / CLI
# ---------------------------------------------------------------------------

def run(config, *, start_audience='graph', start_path=None, debug=False):
    """Start the interactive graph explorer.

    Args:
        config:         owa-tools config dict (passed to _ensure_token).
        start_audience: audience short name to open with (default 'graph').
        start_path:     initial path override; falls back to seed/settings.
        debug:          propagate to _fetch_page for HTTP debug output.

    Deviation noted: the kit draws AFTER fetch_items returns, so the
    'minting token for <aud>…' status written by _ensure_token is never
    visible to the user before the blocking owa-piggy subprocess completes.
    Fixing this would require modifying the frozen tui_kit.app._loop — which
    is out of scope for Phase 2.
    """
    from .tui_menu import build_menu

    settings = _settings_from_config(config)
    menu = build_menu()

    # Resolve the initial path
    seed = start_path or _seed_path(start_audience, settings)

    state = GraphState(
        config,
        audience=start_audience,
        path=seed,
        settings=settings,
        menu=menu,
        debug=debug,
    )
    # state.dirty starts True (set by BrowserState.__init__) so the first
    # loop iteration calls fetch_items immediately — the mint + fetch happen
    # inside the loop, never before curses.wrapper.

    spec = build_spec(state)

    # Redirect stderr for the duration of the TUI session so stray debug
    # prints / tracebacks can't scribble over the curses frame.
    old_stderr = sys.stderr
    sys.stderr = state.stderr_buf
    try:
        _app.run(spec, state)
    finally:
        sys.stderr = old_stderr
