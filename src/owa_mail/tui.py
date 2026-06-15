"""Interactive curses browser for owa-mail.

A small, dependency-free TUI (stdlib `curses` / `webbrowser` / `textwrap`)
for the human side of mail: arrow through a folder, read a full body with
its links intact, and take a couple of safe actions. It is deliberately
not a full client - no compose, no delete - and refuses to run without a
real terminal (see `cmd_tui` in cli.py), since the suite captures stdout
as JSON in `--agent` mode.

Layout logic lives in the pure tui_layout helpers; tui_sort, tui_settings,
tui_dates, and tui_menu handle sorting, settings persistence, date
formatting, and the esc overlay menu respectively. The curses event loop
lives in _loop().
"""
import curses
import webbrowser
from dataclasses import replace as _dc_replace

from . import api as api_mod
from . import folders as folders_mod
from . import messages as messages_mod
from .config import save_config as _save_config
from .format import format_message_pretty
from .tui_dates import validate_custom_format as _validate_custom_format
from .tui_layout import PLACEMENT_OFF
from .tui_layout import list_row as _layout_list_row
from .tui_layout import regions as _regions
from .tui_layout import wrap_body as _wrap_body
from .tui_menu import Menu
from .tui_settings import DEFAULTS as _SETTINGS_DEFAULTS
from .tui_settings import cycle as _cycle_setting
from .tui_settings import from_config as _settings_from_config
from .tui_settings import to_config_dict as _settings_to_config_dict
from .tui_sort import sort_messages as _sort_messages

# How many messages to pull per list fetch. A single page keeps the TUI
# snappy; the list is the newest N, newest first.
PAGE_SIZE = 50

HELP_LINE = (
    'j/k move  l/Tab pane  Enter full  u/d half-page  o browser  r read  / search  Esc menu  q quit'
)
PANE_HELP_LINE = (
    'j/k scroll  u/d half-page  Tab/h/← back to list  g/G top/bot  Enter full  o browser  q quit'
)


# ---------------------------------------------------------------------------
# Pure layout helpers (terminal-free, unit-tested)
# ---------------------------------------------------------------------------

def list_row(msg, width, *, date_fmt='iso8601', custom_fmt=''):
    """Render one message as a single flex-width list row.

    Delegates to tui_layout.list_row which formats columns according to the
    chosen date_fmt (iso8601, ddmm, ddmm_hhmm, or custom).
    """
    return _layout_list_row(msg, width, date_fmt=date_fmt, custom_fmt=custom_fmt)


def reader_lines(message, width):
    """Wrap a single message's pretty rendering to `width` columns.

    Reuses `format.format_message_pretty`, so the body is HTML-flattened
    with link footnotes already appended. Delegates line-wrapping to
    tui_layout.wrap_body for consistency with the reading pane.
    """
    text = format_message_pretty(message)
    return _wrap_body(text, width)


# ---------------------------------------------------------------------------
# Network helpers (thin wrappers over the existing api surface)
# ---------------------------------------------------------------------------

def _fetch_list(api_base, token, folder, search, debug):
    """Fetch the newest PAGE_SIZE messages for a folder (optionally a
    KQL search), normalised and sorted newest-first. Returns None on a
    recoverable API failure (the api layer already reported it)."""
    params = messages_mod.build_list_query(search=search, limit=PAGE_SIZE)
    path = folders_mod.folder_messages_path(folder)
    data = api_mod.api_get(
        api_base, f'{path}?{api_mod.build_query(params)}', token, debug=debug,
    )
    if data is None:
        return None
    items = messages_mod.normalize_messages(data, keep_body=False)
    items.sort(key=lambda m: m.get('received') or '', reverse=True)
    return items


def _fetch_body(api_base, token, message_id, debug):
    """Fetch one message with its body + headers, normalised. None on
    failure."""
    q = api_mod.build_query({'$select': messages_mod.SHOW_SELECT})
    raw = api_mod.api_get(
        api_base, f'{messages_mod.message_path(message_id)}?{q}', token, debug=debug,
    )
    if raw is None:
        return None
    return messages_mod.normalize_message(raw)


def _set_read(api_base, token, message_id, read, debug):
    """PATCH IsRead for one message. Returns True on success."""
    patch = messages_mod.build_mark_patch(read=read)
    result = api_mod.api_request(
        'PATCH', api_base, messages_mod.message_path(message_id), token,
        body=patch, debug=debug,
    )
    return result is not None


# ---------------------------------------------------------------------------
# Curses event loop
# ---------------------------------------------------------------------------

def _safe_addstr(win, y, x, text, attr=0):
    """addstr that clips to the window width and never raises.

    curses raises if you write to (or past) the bottom-right cell; we'd
    rather silently clip than crash a viewer."""
    height, width = win.getmaxyx()
    if y < 0 or y >= height or x >= width:
        return
    text = text[: max(width - x - 1, 0)]
    try:
        win.addstr(y, x, text, attr)
    except curses.error:
        pass


def _prompt(stdscr, label):
    """Read a line of input at the bottom of the screen. Returns the
    string (possibly empty) or None if the user pressed Esc."""
    height, width = stdscr.getmaxyx()
    curses.curs_set(1)
    curses.echo()
    _safe_addstr(stdscr, height - 1, 0, ' ' * (width - 1))
    _safe_addstr(stdscr, height - 1, 0, label)
    stdscr.refresh()
    try:
        raw = stdscr.getstr(height - 1, len(label), max(width - len(label) - 1, 1))
    finally:
        curses.noecho()
        curses.curs_set(0)
    if raw is None:
        return None
    return raw.decode('utf-8', 'replace').strip()


def _pad(s, width):
    """Left-justify *s* to exactly *width* characters."""
    if len(s) >= width:
        return s[:width]
    return s + ' ' * (width - len(s))


def _truncate(s, n):
    """Hard-truncate *s* to at most *n* characters."""
    if n <= 0:
        return ''
    return s[:n]


class _State:
    """Mutable view state for the loop. Plain attributes, no logic."""

    def __init__(self, messages, folder, settings):
        self.messages = messages
        self.folder = folder
        self.search = ''
        self.selected = 0
        self.top = 0           # first visible list row
        self.mode = 'list'     # 'list' | 'reader'
        self.focus = 'list'    # 'list' | 'pane' — which region j/k/u/d drive
        self.reader = []       # wrapped lines for the open message
        self.reader_top = 0
        self.pane_top = 0      # scroll offset within the reading pane
        self.body_cache = {}   # message id -> full normalised message (with body)
        self.status = ''
        self.settings = settings
        self.menu_open = False
        self.menu = Menu(screen='top')


def _sorted_messages(state):
    """Return a sorted copy of state.messages using current settings."""
    return _sort_messages(state.messages, state.settings.sort_by)


def _draw_list(stdscr, state):
    stdscr.erase()
    height, width = stdscr.getmaxyx()
    label = state.folder or 'Inbox'
    if state.search:
        label += f'  search:"{state.search}"'
    unread = sum(1 for m in state.messages if not m.get('is_read'))
    header = f' owa-mail  {label}  ({len(state.messages)} msgs, {unread} unread)'
    _safe_addstr(stdscr, 0, 0, _pad(header, width - 1), curses.A_REVERSE)

    # Compute layout regions for the list pane
    rg = _regions(
        width, height - 2,  # subtract header + footer rows
        state.settings.reading_pane,
        state.settings.split_ratio,
    )
    list_rect = rg.list_rect
    pane_rect = rg.pane_rect

    # list_rect is relative to the content area (row 1 is header, so offset by 1)
    list_w = max(list_rect.w, 1)
    list_h = list_rect.h

    # Scroll to keep selected in view
    body_h = list_h  # visible list rows
    if state.selected < state.top:
        state.top = state.selected
    elif state.selected >= state.top + body_h:
        state.top = state.selected - body_h + 1

    # Sort messages for display
    sorted_msgs = _sorted_messages(state)

    if not sorted_msgs:
        _safe_addstr(stdscr, 2, list_rect.x, '(no messages)')
    for i in range(body_h):
        idx = state.top + i
        if idx >= len(sorted_msgs):
            break
        msg = sorted_msgs[idx]
        is_selected = (idx == state.selected)
        attr = curses.A_REVERSE if is_selected else 0
        if not msg.get('is_read'):
            attr |= curses.A_BOLD
        row = list_row(
            msg, list_w,
            date_fmt=state.settings.date_format,
            custom_fmt=state.settings.date_custom,
        )
        _safe_addstr(stdscr, 1 + i, list_rect.x, _pad(row, list_w), attr)

    # Draw reading pane if enabled
    pane_on = state.settings.reading_pane != PLACEMENT_OFF and pane_rect.w > 0
    if pane_on:
        _draw_reading_pane(stdscr, state, pane_rect, sorted_msgs, height)

    default_help = PANE_HELP_LINE if (pane_on and state.focus == 'pane') else HELP_LINE
    footer = state.status or default_help
    _safe_addstr(
        stdscr, height - 1, 0,
        _pad(_truncate(footer, width - 1), width - 1),
        curses.A_REVERSE,
    )
    stdscr.refresh()


def _draw_reading_pane(stdscr, state, pane_rect, sorted_msgs, full_height):
    """Draw the selected message body in the reading pane."""
    pane_x = pane_rect.x
    pane_y = pane_rect.y + 1  # +1 for header row
    pane_w = pane_rect.w
    pane_h = pane_rect.h

    if pane_w <= 0 or pane_h <= 0:
        return

    # Draw divider (one column to the left of the pane for 'right' layout,
    # or one row above for 'bottom' layout). Bold it when the pane is focused
    # so it's obvious where j/k/u/d are going.
    height, width = stdscr.getmaxyx()
    div_attr = curses.A_BOLD if state.focus == 'pane' else 0
    if state.settings.reading_pane == 'right' and pane_x > 0:
        div_x = pane_x - 1
        for row in range(1, full_height - 1):
            _safe_addstr(stdscr, row, div_x, '│', div_attr)
    elif state.settings.reading_pane == 'bottom' and pane_y > 1:
        div_y = pane_y - 1
        _safe_addstr(stdscr, div_y, 0, '─' * (width - 1), div_attr)

    if not sorted_msgs:
        return
    if state.selected >= len(sorted_msgs):
        return

    # Prefer the cached full message (with body); fall back to the list item
    # (headers only) while the body is still loading.
    msg = sorted_msgs[state.selected]
    full = state.body_cache.get(msg.get('id'), msg)
    text = format_message_pretty(full)
    lines = _wrap_body(text, max(pane_w - 1, 1))

    # Clamp the pane scroll offset to the wrapped body length.
    total = len(lines)
    state.pane_top = max(0, min(state.pane_top, max(total - pane_h, 0)))

    for i in range(pane_h):
        idx = state.pane_top + i
        if idx >= total:
            break
        _safe_addstr(stdscr, pane_y + i, pane_x, lines[idx])

    # A small scroll indicator when the body overflows the pane.
    if total > pane_h:
        end = min(state.pane_top + pane_h, total)
        ind = f'{state.pane_top + 1}-{end}/{total}'
        _safe_addstr(
            stdscr, pane_y, max(pane_x, pane_x + pane_w - len(ind) - 1),
            ind, curses.A_DIM,
        )


def _draw_reader(stdscr, state):
    stdscr.erase()
    height, width = stdscr.getmaxyx()
    body_h = height - 2
    total = len(state.reader)
    state.reader_top = max(0, min(state.reader_top, max(total - body_h, 0)))
    pos = f'{state.reader_top + 1}-{min(state.reader_top + body_h, total)}/{total}'
    _safe_addstr(stdscr, 0, 0, _pad(f' reading  ({pos} lines)', width - 1), curses.A_REVERSE)
    for i in range(body_h):
        idx = state.reader_top + i
        if idx >= total:
            break
        _safe_addstr(stdscr, 1 + i, 0, state.reader[idx])
    footer = state.status or 'j/k scroll  space page  o browser  r read/unread  q/Esc back'
    _safe_addstr(stdscr, height - 1, 0, _pad(_truncate(footer, width - 1), width - 1), curses.A_REVERSE)
    stdscr.refresh()


def _draw_menu(stdscr, state):
    """Blit the overlay menu centered on screen."""
    height, width = stdscr.getmaxyx()
    lines = state.menu.render(width, height, state.settings)
    for y, line in enumerate(lines):
        if y >= height:
            break
        _safe_addstr(stdscr, y, 0, line, curses.A_NORMAL)
    stdscr.refresh()


def _ensure_selected_body(stdscr, state, api_base, token, debug):
    """Lazily fetch + cache the body of the selected message so the reading
    pane can show it. No-op if already cached or nothing is selected."""
    if not state.messages:
        return
    sorted_msgs = _sorted_messages(state)
    if state.selected >= len(sorted_msgs):
        return
    mid = sorted_msgs[state.selected].get('id')
    if not mid or mid in state.body_cache:
        return
    state.status = 'loading…'
    _draw_list(stdscr, state)  # show the loading hint + headers immediately
    full = _fetch_body(api_base, token, mid, debug)
    state.status = ''
    if full is not None:
        state.body_cache[mid] = full


def _move_selection(state, delta):
    """Move the list cursor by *delta*, clamped, resetting pane scroll on
    an actual change so a new message starts at its top."""
    n = len(state.messages)
    if n == 0:
        return
    new = max(0, min(state.selected + delta, n - 1))
    if new != state.selected:
        state.selected = new
        state.pane_top = 0


def _open_selected(stdscr, state, api_base, token, debug):
    """Load the selected message body and switch to reader mode."""
    if not state.messages:
        return
    sorted_msgs = _sorted_messages(state)
    if state.selected >= len(sorted_msgs):
        return
    msg = sorted_msgs[state.selected]
    state.status = 'loading…'
    _draw_list(stdscr, state)
    full = _fetch_body(api_base, token, msg.get('id'), debug)
    state.status = ''
    if full is None:
        state.status = 'failed to load message'
        return
    height, width = stdscr.getmaxyx()
    state.reader = reader_lines(full, width - 1)
    state.reader_top = 0
    state.mode = 'reader'


def _toggle_read(state, api_base, token, debug):
    if not state.messages:
        return
    sorted_msgs = _sorted_messages(state)
    if state.selected >= len(sorted_msgs):
        return
    msg = sorted_msgs[state.selected]
    target = not msg.get('is_read')
    if _set_read(api_base, token, msg.get('id'), target, debug):
        msg['is_read'] = target
        state.status = 'marked ' + ('read' if target else 'unread')
    else:
        state.status = 'failed to update'


def _open_browser(state):
    sorted_msgs = _sorted_messages(state)
    msg = sorted_msgs[state.selected] if sorted_msgs else {}
    link = msg.get('web_link')
    if link:
        webbrowser.open(link)
        state.status = 'opened in browser'
    else:
        state.status = 'no web link for this message'


def _do_search(stdscr, state, api_base, token, debug):
    query = _prompt(stdscr, 'search: ')
    if query is None:
        return
    state.status = 'searching…'
    _draw_list(stdscr, state)
    items = _fetch_list(api_base, token, state.folder, query, debug)
    if items is None:
        state.status = 'search failed'
        return
    state.search = query
    state.messages = items
    state.selected = 0
    state.top = 0
    state.focus = 'list'
    state.pane_top = 0
    state.status = ''


def _persist_settings(state, config):
    """Write settings to disk whenever a value changes."""
    new_vals = _settings_to_config_dict(state.settings)
    config.update(new_vals)
    _save_config(config)


def _handle_menu_action(stdscr, state, action, config, api_base, token, debug):
    """Process the action returned by Menu.select(). Returns True to quit."""
    if action == 'resume':
        state.menu_open = False
    elif action == 'quit':
        return True
    elif action == 'open_settings':
        state.menu.open_settings()
    elif action == 'back':
        state.menu.back()
    elif action == 'help':
        state.menu_open = False
        state.status = HELP_LINE
    elif action == 'reset_settings':
        state.settings = _SETTINGS_DEFAULTS
        _persist_settings(state, config)
        state.status = 'settings reset to defaults'
    elif action.startswith('cycle:'):
        field = action[len('cycle:'):]
        state.settings = _cycle_setting(state.settings, field)
        _persist_settings(state, config)
    elif action == 'edit_custom':
        val = _prompt(stdscr, 'strftime format (e.g. %d %b %H:%M): ')
        if val is not None:
            if val == '' or _validate_custom_format(val):
                state.settings = _dc_replace(state.settings, date_custom=val)
                if val:
                    # Also switch date_format to 'custom'
                    state.settings = _dc_replace(state.settings, date_format='custom')
                _persist_settings(state, config)
            else:
                state.status = f'invalid strftime format: {val!r}'
    return False


def _loop(stdscr, state, api_base, token, debug, config):
    curses.curs_set(0)
    try:
        curses.use_default_colors()
        curses.init_pair(1, -1, -1)
        stdscr.bkgd(' ', curses.color_pair(1))
    except curses.error:
        pass
    stdscr.keypad(True)
    while True:
        # Lazily load the selected message body so the reading pane shows it.
        if (
            not state.menu_open and state.mode == 'list'
            and state.settings.reading_pane != PLACEMENT_OFF
        ):
            _ensure_selected_body(stdscr, state, api_base, token, debug)

        if state.menu_open:
            _draw_menu(stdscr, state)
        elif state.mode == 'list':
            _draw_list(stdscr, state)
        else:
            _draw_reader(stdscr, state)
        ch = stdscr.getch()
        # Any keypress clears a transient status line on the next redraw.
        prev_status = state.status
        state.status = ''

        if state.menu_open:
            if ch in (ord('j'), curses.KEY_DOWN):
                state.menu.move(1)
            elif ch in (ord('k'), curses.KEY_UP):
                state.menu.move(-1)
            elif ch in (curses.KEY_ENTER, 10, 13):
                action = state.menu.select(state.settings)
                if _handle_menu_action(stdscr, state, action, config, api_base, token, debug):
                    return
            elif ch == 27:  # Esc
                if state.menu.screen == 'top':
                    state.menu_open = False
                else:
                    state.menu.back()
            else:
                state.status = prev_status

        elif state.mode == 'list':
            page = max(stdscr.getmaxyx()[0] - 2, 1)
            half = max(page // 2, 1)
            pane_on = state.settings.reading_pane != PLACEMENT_OFF
            if ch == 27:  # Esc → open menu
                state.menu_open = True
                state.menu = Menu(screen='top')
            elif ch == ord('q'):
                return
            elif ch == ord('\t') and pane_on:
                state.focus = 'pane' if state.focus == 'list' else 'list'
            elif state.focus == 'pane' and pane_on:
                # Focus is in the reading pane: j/k/u/d scroll the body.
                if ch in (ord('h'), curses.KEY_LEFT):
                    state.focus = 'list'
                elif ch in (ord('j'), curses.KEY_DOWN):
                    state.pane_top += 1
                elif ch in (ord('k'), curses.KEY_UP):
                    state.pane_top = max(state.pane_top - 1, 0)
                elif ch == ord('d'):
                    state.pane_top += half
                elif ch == ord('u'):
                    state.pane_top = max(state.pane_top - half, 0)
                elif ch == ord('g'):
                    state.pane_top = 0
                elif ch == ord('G'):
                    state.pane_top = 10 ** 9  # clamped to body length in draw
                elif ch in (curses.KEY_ENTER, 10, 13):
                    _open_selected(stdscr, state, api_base, token, debug)
                elif ch == ord('o'):
                    _open_browser(state)
                elif ch == ord('r'):
                    _toggle_read(state, api_base, token, debug)
                else:
                    state.status = prev_status
            else:
                # Focus is in the list: j/k/u/d move the cursor.
                if ch in (ord('j'), curses.KEY_DOWN):
                    _move_selection(state, 1)
                elif ch in (ord('k'), curses.KEY_UP):
                    _move_selection(state, -1)
                elif ch == ord('d'):
                    _move_selection(state, half)
                elif ch == ord('u'):
                    _move_selection(state, -half)
                elif ch == ord('g'):
                    _move_selection(state, -len(state.messages))
                elif ch == ord('G'):
                    _move_selection(state, len(state.messages))
                elif ch in (curses.KEY_NPAGE, ord(' ')):
                    _move_selection(state, page)
                elif ch == curses.KEY_PPAGE:
                    _move_selection(state, -page)
                elif ch in (ord('l'), curses.KEY_RIGHT):
                    if pane_on:
                        state.focus = 'pane'  # enter reading mode
                    else:
                        _open_selected(stdscr, state, api_base, token, debug)
                elif ch in (curses.KEY_ENTER, 10, 13):
                    _open_selected(stdscr, state, api_base, token, debug)
                elif ch == ord('o'):
                    _open_browser(state)
                elif ch == ord('r'):
                    _toggle_read(state, api_base, token, debug)
                elif ch == ord('/'):
                    _do_search(stdscr, state, api_base, token, debug)
                else:
                    state.status = prev_status  # unknown key: keep status

        else:  # reader mode
            height = stdscr.getmaxyx()[0]
            if ch in (ord('q'), 27, curses.KEY_LEFT):
                state.mode = 'list'
            elif ch in (ord('j'), curses.KEY_DOWN):
                state.reader_top += 1
            elif ch in (ord('k'), curses.KEY_UP):
                state.reader_top -= 1
            elif ch in (curses.KEY_NPAGE, ord(' ')):
                state.reader_top += height - 3
            elif ch == curses.KEY_PPAGE:
                state.reader_top -= height - 3
            elif ch == ord('g'):
                state.reader_top = 0
            elif ch == ord('G'):
                state.reader_top = len(state.reader)
            elif ch == ord('o'):
                _open_browser(state)
            elif ch == ord('r'):
                _toggle_read(state, api_base, token, debug)
            else:
                state.status = prev_status


def run(config, access_token, api_base, folder='', debug=False):
    """Entry point: fetch the first page, then run the curses loop.

    Returns a process exit code. Network/auth errors raised by the api
    layer propagate out of curses.wrapper (which restores the terminal
    first) to the shared top-level handler.
    """
    messages = _fetch_list(api_base, access_token, folder, '', debug)
    if messages is None:
        return 1
    settings = _settings_from_config(config)
    state = _State(messages, folders_mod.resolve_folder_id(folder), settings)
    curses.wrapper(_loop, state, api_base, access_token, debug, config)
    return 0
