"""Generic curses list+detail browser shared by owa-* TUIs.

A tool supplies a :class:`BrowserSpec` (callbacks) plus a :class:`BrowserState`;
this module owns the event loop, scrolling, the list and detail panes, the
esc-menu overlay, the search prompt, resize handling and redraw. Drawing goes
through :mod:`owa_core.tui_kit.screen` (safe + fake-screen-testable), geometry
through :mod:`owa_core.tui_kit.layout`, keys through :mod:`owa_core.tui_kit.keys`.

The callback contract (frozen — adapters depend on these names and shapes):

    render_row(item, width)   -> str           one list row, len <= width
    render_detail(item, width) -> list[str]     wrapped detail-pane lines
    fetch_items(state)        -> None           (re)populate state.items + set
                                                state.status; see invariant
    on_search(state, query)   -> None           '/' entered a query
    on_drill(state, item)     -> None           enter/→ on an item
    on_back(state)            -> bool            ←/backspace; True if it popped
    on_refresh(state)         -> None            'r' pressed
    on_menu_action(state, a)  -> bool            esc-menu action; True to quit
    actions: {keycode: fn(state)}               tool-specific extra keys

Curses-safe invariant: ``fetch_items`` MUST NOT print, write to stderr/stdout,
or raise — it reports its outcome by mutating ``state.items`` and
``state.status``. The loop calls it whenever ``state.dirty`` is set (the first
iteration, and after drill/back/refresh/search set it again), so an adapter
that performs a blocking operation (e.g. minting a token) can render a status
frame *before* the fetch by setting ``state.status`` and ``state.dirty``.
"""
from __future__ import annotations

import curses
from dataclasses import dataclass, field
from typing import Any, Callable

from . import keys as _keys
from . import layout as _layout
from . import screen as _screen


class BrowserState:
    """Mutable state owned by the loop. Adapters may attach extra attributes."""

    def __init__(self, *, settings=None, menu=None, title='', items=None):
        self.settings = settings        # tool Settings (read for pane placement)
        self.menu = menu                 # tui_kit.menu.Menu instance, or None
        self.title = title               # header label for the current level
        self.items = list(items or [])   # opaque item objects
        self.selected = 0
        self.top = 0                     # first visible list row
        self.status = ''                 # transient status line (cleared each key)
        self.focus = 'list'              # 'list' | 'detail'
        self.detail_lines: list[str] = []
        self.detail_top = 0
        self._detail_key: Any = object()  # cache key; sentinel forces first build
        self.menu_open = False
        self.dirty = True                # when True, loop calls fetch_items
        self.running = True

    def current(self):
        """The currently selected item, or ``None`` when the list is empty."""
        if 0 <= self.selected < len(self.items):
            return self.items[self.selected]
        return None


@dataclass
class BrowserSpec:
    """Callbacks defining a tool's browser. See module docstring for the contract."""

    render_row: Callable[[Any, int], str]
    render_detail: Callable[[Any, int], list[str]]
    fetch_items: Callable[[BrowserState], None] | None = None
    on_search: Callable[[BrowserState, str], None] | None = None
    on_drill: Callable[[BrowserState, Any], None] | None = None
    on_back: Callable[[BrowserState], bool] | None = None
    on_refresh: Callable[[BrowserState], None] | None = None
    on_menu_action: Callable[[BrowserState, str], bool] | None = None
    actions: dict = field(default_factory=dict)
    footer: str = "j/k move · enter drill · / search · r refresh · esc menu · q quit"
    empty_text: str = "(empty)"


def run(spec, state):  # pragma: no cover - thin curses.wrapper entry point
    """Enter the curses event loop. Restores the terminal on any exit."""
    curses.wrapper(_loop, state, spec)


# ---------------------------------------------------------------------------
# Geometry / scrolling helpers
# ---------------------------------------------------------------------------

def _placement(state):
    placement = getattr(state.settings, 'reading_pane', _layout.PLACEMENT_OFF)
    ratio = getattr(state.settings, 'split_ratio', 50)
    return placement, ratio


def _clamp_scroll(state, body_h):
    n = len(state.items)
    if state.selected < 0:
        state.selected = 0
    elif state.selected >= n:
        state.selected = max(0, n - 1)
    if state.selected < state.top:
        state.top = state.selected
    elif body_h > 0 and state.selected >= state.top + body_h:
        state.top = state.selected - body_h + 1
    if state.top < 0:
        state.top = 0


def _move(state, delta):
    n = len(state.items)
    if n == 0:
        return
    new = max(0, min(state.selected + delta, n - 1))
    if new != state.selected:
        state.selected = new
        state.detail_top = 0


# ---------------------------------------------------------------------------
# Draw
# ---------------------------------------------------------------------------

def _ensure_detail(state, spec, pane_w):
    item = state.current()
    key = id(item) if item is not None else None
    if key != state._detail_key:
        state.detail_lines = (
            spec.render_detail(item, max(pane_w, 1)) if item is not None else []
        )
        state.detail_top = 0
        state._detail_key = key


def _draw_detail(stdscr, state, spec, rect, placement):
    height, width = stdscr.getmaxyx()
    if placement == _layout.PLACEMENT_RIGHT and rect.x > 0:
        for row in range(1, height - 1):
            _screen.safe_addstr(stdscr, row, rect.x - 1, '│')
        x0, y0 = rect.x, 1
        pane_w, pane_h = rect.w, max(height - 2, 0)
    elif placement == _layout.PLACEMENT_BOTTOM and rect.h > 0:
        # rect.y is in the (height-2) body coordinate space; +0 maps the
        # divider to its screen row because the header occupies row 0.
        _screen.safe_addstr(stdscr, rect.y, 0, '─' * max(width - 1, 0))
        x0, y0 = 0, rect.y + 1
        pane_w, pane_h = width, rect.h
    else:
        return
    _ensure_detail(state, spec, pane_w)
    total = len(state.detail_lines)
    state.detail_top = max(0, min(state.detail_top, max(total - pane_h, 0)))
    for i in range(pane_h):
        idx = state.detail_top + i
        if idx >= total:
            break
        _screen.safe_addstr(stdscr, y0 + i, x0, state.detail_lines[idx])


def _draw(stdscr, state, spec):
    height, width = stdscr.getmaxyx()
    stdscr.erase()
    inner_w = max(width - 1, 0)

    header = f' {state.title}'
    if state.status:
        header = f'{header}  —  {state.status}'
    _screen.safe_addstr(stdscr, 0, 0, _layout.pad(header, inner_w), curses.A_REVERSE)

    placement, ratio = _placement(state)
    rg = _layout.regions(width, height - 2, placement, ratio)
    list_rect, pane_rect = rg.list_rect, rg.pane_rect
    list_w = max(list_rect.w, 1)
    body_h = max(list_rect.h, 0)
    _clamp_scroll(state, body_h)

    if not state.items:
        _screen.safe_addstr(stdscr, 1, list_rect.x, spec.empty_text)
    for i in range(body_h):
        idx = state.top + i
        if idx >= len(state.items):
            break
        selected = (idx == state.selected and state.focus == 'list')
        attr = curses.A_REVERSE if selected else 0
        row = spec.render_row(state.items[idx], list_w)
        _screen.safe_addstr(stdscr, 1 + i, list_rect.x, _layout.pad(row, list_w), attr)

    if placement != _layout.PLACEMENT_OFF and pane_rect.w > 0 and pane_rect.h > 0:
        _draw_detail(stdscr, state, spec, pane_rect, placement)

    _screen.safe_addstr(
        stdscr, height - 1, 0,
        _layout.pad(_layout.truncate(spec.footer, inner_w), inner_w),
        curses.A_REVERSE,
    )
    stdscr.refresh()


def _draw_menu(stdscr, state):
    height, width = stdscr.getmaxyx()
    for y, line in enumerate(state.menu.render(width, height, state.settings)):
        if y >= height:
            break
        _screen.safe_addstr(stdscr, y, 0, line)
    stdscr.refresh()


# ---------------------------------------------------------------------------
# Event loop
# ---------------------------------------------------------------------------

def _apply_menu_action(state, spec, action):
    if action in ('resume', 'none'):
        state.menu_open = False
    elif action == 'open_settings':
        state.menu.open_settings()
    elif action == 'back':
        state.menu.back()
    elif action == 'quit':
        state.running = False
    elif spec.on_menu_action is not None and spec.on_menu_action(state, action):
        state.running = False


def _handle_menu_key(state, spec, ch, prev_status):
    menu = state.menu
    if ch in _keys.DOWN:
        menu.move(1)
        state.status = prev_status
    elif ch in _keys.UP:
        menu.move(-1)
        state.status = prev_status
    elif ch in _keys.ENTER:
        _apply_menu_action(state, spec, menu.select(state.settings))
    elif ch == _keys.ESC:
        if menu.screen == 'top':
            state.menu_open = False
        else:
            menu.back()
        state.status = prev_status
    else:
        state.status = prev_status


def _handle_detail_key(stdscr, state, ch, prev_status):
    half = max((stdscr.getmaxyx()[0] - 2) // 2, 1)
    if ch in _keys.DOWN:
        state.detail_top += 1
    elif ch in _keys.UP:
        state.detail_top = max(0, state.detail_top - 1)
    elif ch in _keys.HALF_DOWN:
        state.detail_top += half
    elif ch in _keys.HALF_UP:
        state.detail_top = max(0, state.detail_top - half)
    elif ch in _keys.BACK:
        state.focus = 'list'
    else:
        state.status = prev_status


def _handle_list_key(stdscr, state, spec, ch, prev_status):
    page = max(stdscr.getmaxyx()[0] - 2, 1)
    half = max(page // 2, 1)
    placement, _ = _placement(state)
    pane_on = placement != _layout.PLACEMENT_OFF

    if ch in _keys.DOWN:
        _move(state, 1)
    elif ch in _keys.UP:
        _move(state, -1)
    elif ch in _keys.HALF_DOWN:
        _move(state, half)
    elif ch in _keys.HALF_UP:
        _move(state, -half)
    elif ch in _keys.PAGE_DOWN:
        _move(state, page)
    elif ch in _keys.PAGE_UP:
        _move(state, -page)
    elif ch in _keys.TOP:
        _move(state, -len(state.items))
    elif ch in _keys.BOTTOM:
        _move(state, len(state.items))
    elif ch in _keys.DRILL:
        item = state.current()
        if pane_on and ch in _keys.RIGHT and item is not None:
            state.focus = 'detail'
        elif item is not None and spec.on_drill is not None:
            spec.on_drill(state, item)
        else:
            state.status = prev_status
    elif ch in _keys.BACK:
        if spec.on_back is None or not spec.on_back(state):
            state.status = prev_status
    elif ch in _keys.SEARCH:
        if spec.on_search is not None:
            query = _screen.prompt(stdscr, 'search: ')
            if query is not None:
                spec.on_search(state, query)
        else:
            state.status = prev_status
    elif ch in _keys.REFRESH:
        if spec.on_refresh is not None:
            spec.on_refresh(state)
        else:
            state.status = prev_status
    elif ch in spec.actions:
        spec.actions[ch](state)
    else:
        state.status = prev_status


def _loop(stdscr, state, spec):
    _screen.init_colors(stdscr)
    while state.running:
        if state.dirty and spec.fetch_items is not None:
            state.dirty = False
            spec.fetch_items(state)

        if state.menu_open and state.menu is not None:
            _draw_menu(stdscr, state)
        else:
            _draw(stdscr, state, spec)

        ch = stdscr.getch()
        prev_status = state.status
        state.status = ''

        if state.menu_open and state.menu is not None:
            _handle_menu_key(state, spec, ch, prev_status)
            continue

        if ch == curses.KEY_RESIZE:
            try:
                curses.resizeterm(*stdscr.getmaxyx())
            except curses.error:
                pass
            stdscr.clear()
            state.status = prev_status
            continue

        if ch in _keys.QUIT:
            state.running = False
        elif ch == _keys.ESC and state.menu is not None:
            state.menu.reset()
            state.menu_open = True
        elif state.focus == 'detail':
            _handle_detail_key(stdscr, state, ch, prev_status)
        else:
            _handle_list_key(stdscr, state, spec, ch, prev_status)
