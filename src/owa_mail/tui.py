"""Interactive curses browser for owa-mail.

A small, dependency-free TUI (stdlib `curses` / `webbrowser` / `textwrap`)
for the human side of mail: arrow through a folder, read a full body with
its links intact, and take a couple of safe actions. It is deliberately
not a full client - no compose, no delete - and refuses to run without a
real terminal (see `cmd_tui` in cli.py), since the suite captures stdout
as JSON in `--agent` mode.

Layout logic lives in the pure `list_row` / `reader_lines` helpers so it
can be unit-tested without a terminal; `run` owns the curses event loop.
"""
import curses
import textwrap
import webbrowser

from owa_core.format import date_part as _date_part
from owa_core.format import pad as _pad
from owa_core.format import time_part as _time_part
from owa_core.format import truncate as _truncate

from . import api as api_mod
from . import folders as folders_mod
from . import messages as messages_mod
from .format import format_message_pretty

# How many messages to pull per list fetch. A single page keeps the TUI
# snappy; the list is the newest N, newest first.
PAGE_SIZE = 50

HELP_LINE = (
    'j/k move  Enter read  o browser  r read/unread  / search  g/G top/bot  q quit'
)


# ---------------------------------------------------------------------------
# Pure layout helpers (terminal-free, unit-tested)
# ---------------------------------------------------------------------------

def list_row(message, width):
    """Render one message as a single fixed-width list row.

    Mirrors the column order of `format.format_messages_pretty`
    (date, time, unread/flag/attachment markers, sender, subject, preview)
    but fits the whole row into `width` so curses never overflows.
    """
    date = _date_part(message.get('received') or '')
    time = _time_part(message.get('received') or '')
    marker = '*' if not message.get('is_read') else ' '
    flag = '!' if message.get('flag') == 'Flagged' else ' '
    att = '@' if message.get('has_attachments') else ' '
    sender = _pad(_truncate(message.get('from') or '', 24), 24)
    subject = _truncate(message.get('subject') or '(no subject)', 40)
    row = f'{date} {time} {marker}{flag}{att} {sender}  {subject}'
    return _truncate(row, max(width, 1))


def reader_lines(message, width):
    """Wrap a single message's pretty rendering to `width` columns.

    Reuses `format.format_message_pretty`, so the body is HTML-flattened
    with link footnotes already appended. Blank lines are preserved; long
    lines (including footnote URLs) are hard-wrapped so they never overflow
    the window.
    """
    width = max(width, 1)
    text = format_message_pretty(message)
    out = []
    for raw in text.split('\n'):
        if not raw.strip():
            out.append('')
            continue
        out.extend(textwrap.wrap(
            raw, width, break_long_words=True, break_on_hyphens=False,
        ) or [''])
    return out


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


class _State:
    """Mutable view state for the loop. Plain attributes, no logic."""

    def __init__(self, messages, folder):
        self.messages = messages
        self.folder = folder
        self.search = ''
        self.selected = 0
        self.top = 0           # first visible list row
        self.mode = 'list'     # 'list' | 'reader'
        self.reader = []       # wrapped lines for the open message
        self.reader_top = 0
        self.status = ''


def _draw_list(stdscr, state):
    stdscr.erase()
    height, width = stdscr.getmaxyx()
    label = state.folder or 'Inbox'
    if state.search:
        label += f'  search:"{state.search}"'
    unread = sum(1 for m in state.messages if not m.get('is_read'))
    header = f' owa-mail  {label}  ({len(state.messages)} msgs, {unread} unread)'
    _safe_addstr(stdscr, 0, 0, _pad(header, width - 1), curses.A_REVERSE)

    body_h = height - 2  # rows available between header and footer
    if state.selected < state.top:
        state.top = state.selected
    elif state.selected >= state.top + body_h:
        state.top = state.selected - body_h + 1

    if not state.messages:
        _safe_addstr(stdscr, 2, 0, '(no messages)')
    for i in range(body_h):
        idx = state.top + i
        if idx >= len(state.messages):
            break
        msg = state.messages[idx]
        attr = curses.A_REVERSE if idx == state.selected else 0
        if not msg.get('is_read'):
            attr |= curses.A_BOLD
        _safe_addstr(stdscr, 1 + i, 0, _pad(list_row(msg, width - 1), width - 1), attr)

    footer = state.status or HELP_LINE
    _safe_addstr(stdscr, height - 1, 0, _pad(_truncate(footer, width - 1), width - 1), curses.A_REVERSE)
    stdscr.refresh()


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


def _open_selected(stdscr, state, api_base, token, debug):
    """Load the selected message body and switch to reader mode."""
    if not state.messages:
        return
    msg = state.messages[state.selected]
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
    msg = state.messages[state.selected]
    target = not msg.get('is_read')
    if _set_read(api_base, token, msg.get('id'), target, debug):
        msg['is_read'] = target
        state.status = 'marked ' + ('read' if target else 'unread')
    else:
        state.status = 'failed to update'


def _open_browser(state):
    msg = state.messages[state.selected] if state.messages else {}
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
    state.status = ''


def _loop(stdscr, state, api_base, token, debug):
    curses.curs_set(0)
    stdscr.keypad(True)
    while True:
        if state.mode == 'list':
            _draw_list(stdscr, state)
        else:
            _draw_reader(stdscr, state)
        ch = stdscr.getch()
        # Any keypress clears a transient status line on the next redraw.
        prev_status = state.status
        state.status = ''

        if state.mode == 'list':
            if ch in (ord('q'), 27):  # q / Esc
                return
            elif ch in (ord('j'), curses.KEY_DOWN):
                state.selected = min(state.selected + 1, max(len(state.messages) - 1, 0))
            elif ch in (ord('k'), curses.KEY_UP):
                state.selected = max(state.selected - 1, 0)
            elif ch == ord('g'):
                state.selected = 0
            elif ch == ord('G'):
                state.selected = max(len(state.messages) - 1, 0)
            elif ch in (curses.KEY_NPAGE, ord(' ')):
                state.selected = min(state.selected + (stdscr.getmaxyx()[0] - 2), max(len(state.messages) - 1, 0))
            elif ch == curses.KEY_PPAGE:
                state.selected = max(state.selected - (stdscr.getmaxyx()[0] - 2), 0)
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
    state = _State(messages, folders_mod.resolve_folder_id(folder))
    curses.wrapper(_loop, state, api_base, access_token, debug)
    return 0
