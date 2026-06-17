"""Interactive curses browser for owa-cal.

A dependency-free TUI (stdlib curses) for browsing calendar events: arrow
through an agenda list, read a full event detail pane, and respond to meeting
invites. It is deliberately read-focused in v1 (no create/update/delete) and
refuses to run without a real terminal (see ``cmd_tui`` in cli.py), since the
suite captures stdout as JSON in ``--agent`` mode.

Token is minted BEFORE curses.wrapper is entered (in cmd_tui), so an auth
failure exits cleanly before the terminal is taken over.
"""
from __future__ import annotations

import curses
import textwrap
import urllib.parse
import webbrowser
from dataclasses import replace as _dc_replace
from datetime import date

from owa_core.errors import OwaError
from owa_core.tui_kit import app as _app
from owa_core.tui_kit import screen as _screen

from . import api as api_mod
from . import events as events_mod
from .config import save_config as _save_config
from .tui_menu import Menu
from .tui_settings import DEFAULTS as _SETTINGS_DEFAULTS
from .tui_settings import cycle as _cycle_setting
from .tui_settings import from_config as _settings_from_config
from .tui_settings import to_config_dict as _settings_to_config_dict

# Default page size for calendarView requests
PAGE_SIZE = 50

# Footer hint lines
HELP_LINE = (
    'j/k move · enter detail · / search · r refresh · a/d/t respond · o browser · esc menu · q quit'
)

# Respond actions supported in the TUI
_RESPOND_ACTIONS = {
    'accept': 'accept',
    'decline': 'decline',
    'tentative': 'tentativelyaccept',
}

# Key shortcuts for respond actions
_KEY_ACCEPT = ord('a')
_KEY_DECLINE = ord('d')
_KEY_TENTATIVE = ord('t')
_KEY_OPEN = ord('o')


# ---------------------------------------------------------------------------
# Period helpers
# ---------------------------------------------------------------------------

def _today_range():
    """Return (from_date, to_date) for today."""
    today = date.today().strftime('%Y-%m-%d')
    return today, today


def _week_range():
    """Return (from_date, to_date) for the current ISO week (Mon-Sun)."""
    from .dates import current_iso_week, iso_week_range
    week, year = current_iso_week()
    return iso_week_range(week, year)


def _month_range():
    """Return (from_date, to_date) for the current calendar month."""
    today = date.today()
    first = today.replace(day=1).strftime('%Y-%m-%d')
    # Last day of month: go to first of next month minus one day
    if today.month == 12:
        last = today.replace(year=today.year + 1, month=1, day=1)
    else:
        last = today.replace(month=today.month + 1, day=1)
    from datetime import timedelta
    last_day = (last - timedelta(days=1)).strftime('%Y-%m-%d')
    return first, last_day


def _range_for_setting(day_range):
    """Resolve a day_range setting value to (from_date, to_date)."""
    if day_range == 'week':
        return _week_range()
    if day_range == 'month':
        return _month_range()
    return _today_range()


# ---------------------------------------------------------------------------
# Row and detail rendering (pure, unit-testable)
# ---------------------------------------------------------------------------

def render_row(event, width):
    """One-line agenda row: time + subject + location/organizer."""
    start = event.get('start') or ''
    # Extract HH:MM from ISO datetime
    if 'T' in start:
        time_part = start.split('T', 1)[1][:5]
    else:
        time_part = start[:5] if start else ''
    end = event.get('end') or ''
    if 'T' in end:
        end_time = end.split('T', 1)[1][:5]
    else:
        end_time = end[:5] if end else ''
    subject = event.get('subject') or ''
    location = event.get('location') or ''
    is_all_day = event.get('isAllDay') or False

    if is_all_day:
        time_col = 'all-day'
    elif time_part and end_time:
        time_col = f'{time_part}-{end_time}'
    elif time_part:
        time_col = time_part
    else:
        time_col = ''

    # Build row: time | subject | location
    time_w = 12
    time_str = time_col[:time_w].ljust(time_w) if time_col else ' ' * time_w
    rest_w = max(width - time_w - 2, 1)

    loc_hint = ''
    if location:
        loc_hint = f'  [{location[:20]}]'

    subj_w = max(rest_w - len(loc_hint), 1)
    subj_str = subject[:subj_w]

    row = f'{time_str}  {subj_str}{loc_hint}'
    return row[:width]


def render_detail(event, width):
    """Multi-line event detail card."""
    lines = []
    subject = event.get('subject') or '(no subject)'
    lines.append(subject[:width])
    lines.append('─' * min(len(subject), width))

    start = event.get('start') or ''
    end = event.get('end') or ''
    is_all_day = event.get('isAllDay') or False
    if is_all_day:
        lines.append(f'When:     all-day  {start[:10]}')
    elif start and end:
        lines.append(f'When:     {start}  -  {end}')
    elif start:
        lines.append(f'When:     {start}')

    location = event.get('location') or ''
    if location:
        lines.append(f'Location: {location[:width - 10]}')

    show_as = event.get('showAs') or ''
    if show_as:
        lines.append(f'Status:   {show_as}')

    categories = event.get('categories') or []
    if categories:
        cat_str = ', '.join(categories)
        lines.append(f'Category: {cat_str[:width - 10]}')

    organizer = event.get('organizer') or ''
    if organizer:
        lines.append(f'Organizer:{organizer[:width - 10]}')

    attendees = event.get('attendees') or []
    if attendees:
        lines.append('')
        lines.append('Attendees:')
        for att in attendees[:10]:  # cap at 10 for readability
            att_str = str(att)[:width - 4]
            lines.append(f'  {att_str}')

    body = (event.get('body') or '').strip()
    if body:
        lines.append('')
        lines.append('Body:')
        # Wrap body text to width
        for para in body.splitlines():
            if not para.strip():
                lines.append('')
                continue
            for wrapped in textwrap.wrap(para, width - 2) or ['']:
                lines.append(f'  {wrapped}')

    # Show event ID at the bottom for reference
    event_id = event.get('id') or ''
    if event_id:
        lines.append('')
        id_preview = event_id[:30] + '...' if len(event_id) > 30 else event_id
        lines.append(f'ID: {id_preview}')

    return lines


# ---------------------------------------------------------------------------
# Fetch helpers (curses-safe: no raises, no prints)
# ---------------------------------------------------------------------------

def _build_event_query(access_token, api_base, from_date, to_date, debug):
    """Fetch events for a date range. Returns list or empty list on failure."""
    start_dt = f'{from_date}T00:00:00'
    end_dt = f'{to_date}T23:59:59'
    q = api_mod.build_query({
        'startDateTime': start_dt,
        'endDateTime': end_dt,
        '$top': PAGE_SIZE,
        '$orderby': 'Start/DateTime',
        '$select': (
            'Id,Subject,Start,End,Location,Categories,ShowAs,IsAllDay,'
            'OriginalStartTimeZone,OriginalEndTimeZone,Organizer,Attendees,Body'
        ),
    })
    return f'me/calendarView?{q}'


def fetch_items(state):
    """Populate state.items with events for the current period.

    Curses-safe: never raises, never prints. Sets state.status on error.
    """
    try:
        access_token = state.access_token
        api_base = state.api_base
        debug = getattr(state, 'debug', False)
        day_range = getattr(state.settings, 'day_range', 'today')
        from_date, to_date = _range_for_setting(day_range)

        query_path = _build_event_query(access_token, api_base, from_date, to_date, debug)
        data = api_mod.api_get(api_base, query_path, access_token, debug=debug)
        if data is None:
            state.status = 'fetch failed'
            return

        normalized = events_mod.normalize_events(data)

        # Filter declined events if show_declined == 'no'
        show_declined = getattr(state.settings, 'show_declined', 'no')
        if show_declined == 'no':
            normalized = [
                e for e in normalized
                if (e.get('showAs') or '').lower() != 'free'
                or (e.get('categories') or [])  # keep if categorised
            ]

        # Apply current search filter if any
        search = getattr(state, '_search', '')
        if search:
            needle = search.lower()
            normalized = [
                e for e in normalized
                if needle in (e.get('subject') or '').lower()
                or any(needle in str(att).lower() for att in (e.get('attendees') or []))
            ]

        state.items = normalized
        state.title = f'owa-cal  {from_date}' + (f' – {to_date}' if to_date != from_date else '')
    except OwaError as exc:
        state.status = f'error: {exc}'
    except Exception as exc:  # noqa: BLE001
        state.status = f'unexpected error: {exc}'


# ---------------------------------------------------------------------------
# Callback handlers
# ---------------------------------------------------------------------------

def on_search(state, query):
    """Filter events by subject/attendee (client-side)."""
    state._search = query
    state.dirty = True


def on_refresh(state):
    """Re-fetch the current period."""
    state.dirty = True
    state.status = 'refreshing…'


def on_drill(state, item):
    """Focus detail pane on the selected event (no-op if pane is already shown)."""
    state.focus = 'detail'


def on_back(state):
    """No stack navigation in v1; return False (nothing popped)."""
    return False


def on_menu_action(state, action):
    """Handle menu actions including settings cycle and help."""
    if action == 'help':
        state.menu_open = False
        state.status = HELP_LINE
        return False
    if action == 'reset_settings':
        state.settings = _SETTINGS_DEFAULTS
        _persist_settings(state)
        state.status = 'settings reset to defaults'
        return False
    if action.startswith('cycle:'):
        field = action[len('cycle:'):]
        state.settings = _cycle_setting(state.settings, field)
        _persist_settings(state)
        return False
    return False


def _persist_settings(state):
    """Write settings to disk when a value changes."""
    config = getattr(state, '_config', {})
    new_vals = _settings_to_config_dict(state.settings)
    config.update(new_vals)
    try:
        _save_config(config)
    except Exception:  # noqa: BLE001
        pass  # best-effort, never crash the TUI


# ---------------------------------------------------------------------------
# Respond action (mutates — requires explicit confirm keypress)
# ---------------------------------------------------------------------------

def _do_respond(stdscr, state, action_key):
    """Respond to the selected event's invite after an explicit confirm prompt.

    action_key is one of 'accept', 'decline', 'tentative'.
    """
    item = state.current()
    if item is None:
        state.status = 'no event selected'
        return

    event_id = item.get('id') or ''
    subject = item.get('subject') or '(no subject)'
    if not event_id:
        state.status = 'event has no id'
        return

    # Show confirm prompt before sending. The prompt touches curses (curs_set/
    # getstr/echo); guard it so a curses.error on a tiny terminal can't escape
    # the loop and tear down the wrapper mid-frame.
    prompt_text = f'{action_key} "{subject[:30]}"? (y/N): '
    try:
        answer = _screen.prompt(stdscr, prompt_text)
    except Exception:
        state.status = 'prompt error'
        return
    if answer is None or answer.strip().lower() not in ('y', 'yes'):
        state.status = 'cancelled'
        return

    access_token = state.access_token
    api_base = state.api_base
    debug = getattr(state, 'debug', False)

    # Map action_key to Outlook REST endpoint segment
    rest_action = _RESPOND_ACTIONS[action_key]
    endpoint = (
        f'me/events/{urllib.parse.quote(event_id, safe="")}/{rest_action}'
    )
    body = {'Comment': '', 'SendResponse': True}
    try:
        result = api_mod.api_request(
            'POST', api_base, endpoint, access_token, body=body, debug=debug,
        )
    except OwaError as exc:
        state.status = f'respond failed: {exc}'
        return

    if result is None:
        state.status = 'respond failed'
        return

    state.status = f'{action_key}ed: {subject[:30]}'
    # Re-fetch to reflect updated status
    state.dirty = True


def _do_open_browser(state):
    """Open the selected event in the browser (via webLink if available)."""
    item = state.current()
    if item is None:
        state.status = 'no event selected'
        return
    link = item.get('webLink') or item.get('web_link') or ''
    if link:
        try:
            # Silence OS fds so a browser-launcher diagnostic can't corrupt the
            # curses frame (the launcher's child inherits fds 1/2).
            with _screen.silence_os_fds():
                webbrowser.open(link)
            state.status = 'opened in browser'
        except Exception:  # noqa: BLE001
            state.status = 'could not open browser'
    else:
        state.status = 'no web link for this event'


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def build_session(config, access_token, api_base, *, debug=False, day_range=''):
    """Build the (spec, state) pair the loop runs on — pure, no curses.

    A caller-supplied ``day_range`` (today/week/month) overrides the persisted
    setting. The respond actions stash a sentinel on ``state._pending_respond``
    rather than acting directly, because the kit's ``actions[key](state)``
    contract passes no ``stdscr`` and the confirm prompt needs one — the loop
    drains the sentinel with ``stdscr`` in hand (see ``_cal_loop``).
    """
    settings = _settings_from_config(config)
    if day_range in ('today', 'week', 'month'):
        settings = _dc_replace(settings, day_range=day_range)

    state = _app.BrowserState(settings=settings, menu=Menu(screen='top'), title='owa-cal')
    state.access_token = access_token
    state.api_base = api_base
    state.debug = debug
    state._config = config
    state._search = ''
    state._pending_respond = None

    spec = _app.BrowserSpec(
        render_row=render_row,
        render_detail=render_detail,
        fetch_items=fetch_items,
        on_search=on_search,
        on_drill=on_drill,
        on_back=on_back,
        on_refresh=on_refresh,
        on_menu_action=on_menu_action,
        actions={
            _KEY_ACCEPT: lambda st: setattr(st, '_pending_respond', 'accept'),
            _KEY_DECLINE: lambda st: setattr(st, '_pending_respond', 'decline'),
            _KEY_TENTATIVE: lambda st: setattr(st, '_pending_respond', 'tentative'),
            _KEY_OPEN: _do_open_browser,
        },
        footer=HELP_LINE,
        empty_text='(no events)',
    )
    return spec, state


def _cal_loop(stdscr, state, spec):  # pragma: no cover - curses loop (cf. kit app._loop)
    """The kit's event loop plus a respond-sentinel drain that needs stdscr."""
    from owa_core.tui_kit import app as _app_mod
    from owa_core.tui_kit import screen as _scr
    _scr.init_colors(stdscr)
    while state.running:
        if state.dirty and spec.fetch_items is not None:
            state.dirty = False
            spec.fetch_items(state)

        if state._pending_respond:
            action = state._pending_respond
            state._pending_respond = None
            _do_respond(stdscr, state, action)
            continue

        if state.menu_open and state.menu is not None:
            _app_mod._draw_menu(stdscr, state)
        else:
            _app_mod._draw(stdscr, state, spec)

        ch = stdscr.getch()
        prev_status = state.status
        state.status = ''

        if state.menu_open and state.menu is not None:
            _app_mod._handle_menu_key(state, spec, ch, prev_status)
            continue

        if ch == curses.KEY_RESIZE:
            try:
                curses.resizeterm(*stdscr.getmaxyx())
            except curses.error:
                pass
            stdscr.clear()
            state.status = prev_status
            continue

        if ch in _app_mod._keys.QUIT:
            state.running = False
        elif ch == _app_mod._keys.ESC and state.menu is not None:
            state.menu.reset()
            state.menu_open = True
        elif state.focus == 'detail':
            _app_mod._handle_detail_key(stdscr, state, ch, prev_status)
        else:
            _app_mod._handle_list_key(stdscr, state, spec, ch, prev_status)


def run(config, access_token, api_base, *, debug=False, day_range=''):  # pragma: no cover - curses entry
    """Build the session and enter the curses loop. Returns a process exit code.

    The token is already minted by cmd_tui before this is called, so no auth
    work happens here.
    """
    spec, state = build_session(
        config, access_token, api_base, debug=debug, day_range=day_range)
    curses.wrapper(_cal_loop, state, spec)
    return 0
