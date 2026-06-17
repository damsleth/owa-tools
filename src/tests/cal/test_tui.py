"""Tests for owa_cal.tui: callbacks, render functions, and respond action.

Tests are cal-specific behaviour only; kit-level navigation coverage lives
in src/tests/core/tui_kit/. Uses FakeScreen from conftest.py.
"""
from __future__ import annotations

from owa_cal.tui import (
    _do_respond,
    fetch_items,
    on_back,
    on_drill,
    on_refresh,
    on_search,
    render_detail,
    render_row,
)
from owa_core.tui_kit.app import BrowserState

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _Settings:
    reading_pane = 'right'
    split_ratio = 50
    day_range = 'today'
    show_declined = 'no'


def _make_event(**kwargs):
    base = {
        'id': 'evt-001',
        'subject': 'Team standup',
        'start': '2026-06-17T09:00:00',
        'end': '2026-06-17T09:30:00',
        'location': 'Teams',
        'categories': [],
        'showAs': 'Busy',
        'isAllDay': False,
        'organizer': 'boss@example.com',
        'attendees': ['me@example.com', 'boss@example.com'],
        'body': 'Daily sync call.',
    }
    base.update(kwargs)
    return base


def _make_state(events=None, token='tok', api_base='https://example.com'):
    state = BrowserState(settings=_Settings(), title='owa-cal')
    state.access_token = token
    state.api_base = api_base
    state.debug = False
    state._config = {}
    state._search = ''
    state._respond_mode = False
    if events is not None:
        state.items = events
    return state


# ---------------------------------------------------------------------------
# render_row
# ---------------------------------------------------------------------------

class TestRenderRow:
    def test_basic_row(self):
        evt = _make_event()
        row = render_row(evt, 80)
        assert '09:00' in row
        assert 'Team standup' in row

    def test_row_truncated_to_width(self):
        evt = _make_event(subject='A' * 200)
        row = render_row(evt, 40)
        assert len(row) <= 40

    def test_all_day_event(self):
        evt = _make_event(isAllDay=True)
        row = render_row(evt, 80)
        assert 'all-day' in row

    def test_location_shown(self):
        evt = _make_event(location='Room 101')
        row = render_row(evt, 80)
        assert 'Room 101' in row

    def test_empty_subject(self):
        evt = _make_event(subject='')
        row = render_row(evt, 80)
        # Should not crash; time_col still shown
        assert isinstance(row, str)

    def test_width_one(self):
        evt = _make_event()
        row = render_row(evt, 1)
        assert len(row) <= 1


# ---------------------------------------------------------------------------
# render_detail
# ---------------------------------------------------------------------------

class TestRenderDetail:
    def test_subject_in_detail(self):
        evt = _make_event()
        lines = render_detail(evt, 80)
        assert any('Team standup' in ln for ln in lines)

    def test_time_range_shown(self):
        evt = _make_event()
        lines = render_detail(evt, 80)
        assert any('09:00' in ln for ln in lines)

    def test_location_shown(self):
        evt = _make_event()
        lines = render_detail(evt, 80)
        assert any('Teams' in ln for ln in lines)

    def test_organizer_shown(self):
        evt = _make_event()
        lines = render_detail(evt, 80)
        assert any('boss@example.com' in ln for ln in lines)

    def test_body_shown(self):
        evt = _make_event()
        lines = render_detail(evt, 80)
        assert any('Daily sync call' in ln for ln in lines)

    def test_all_day_label(self):
        evt = _make_event(isAllDay=True)
        lines = render_detail(evt, 80)
        assert any('all-day' in ln for ln in lines)

    def test_returns_list_of_strings(self):
        evt = _make_event()
        lines = render_detail(evt, 80)
        assert isinstance(lines, list)
        assert all(isinstance(ln, str) for ln in lines)


# ---------------------------------------------------------------------------
# fetch_items
# ---------------------------------------------------------------------------

class TestFetchItems:
    def test_populates_items_on_success(self, monkeypatch):
        from owa_cal import api as api_mod
        evt = _make_event()
        monkeypatch.setattr(
            api_mod, 'api_get',
            lambda *a, **kw: {'value': [
                {'Id': evt['id'], 'Subject': evt['subject'],
                 'Start': {'DateTime': '2026-06-17T09:00:00', 'TimeZone': 'UTC'},
                 'End': {'DateTime': '2026-06-17T09:30:00', 'TimeZone': 'UTC'},
                 'Location': {'DisplayName': ''},
                 'Categories': [], 'ShowAs': 'Busy', 'IsAllDay': False}
            ]},
        )
        state = _make_state()
        fetch_items(state)
        assert len(state.items) >= 1
        assert state.status == ''

    def test_api_failure_sets_status(self, monkeypatch):
        from owa_cal import api as api_mod
        monkeypatch.setattr(api_mod, 'api_get', lambda *a, **kw: None)
        state = _make_state()
        fetch_items(state)
        assert state.status == 'fetch failed'
        # items unchanged (empty)
        assert state.items == []

    def test_does_not_raise_on_error(self, monkeypatch):
        from owa_cal import api as api_mod
        monkeypatch.setattr(api_mod, 'api_get', lambda *a, **kw: None)
        state = _make_state()
        # Must not raise
        fetch_items(state)

    def test_search_filter_applied(self, monkeypatch):
        from owa_cal import api as api_mod
        monkeypatch.setattr(
            api_mod, 'api_get',
            lambda *a, **kw: {'value': [
                {'Id': 'e1', 'Subject': 'Budget review',
                 'Start': {'DateTime': '2026-06-17T10:00:00', 'TimeZone': 'UTC'},
                 'End': {'DateTime': '2026-06-17T11:00:00', 'TimeZone': 'UTC'},
                 'Location': {'DisplayName': ''}, 'Categories': [],
                 'ShowAs': 'Busy', 'IsAllDay': False},
                {'Id': 'e2', 'Subject': 'Team standup',
                 'Start': {'DateTime': '2026-06-17T09:00:00', 'TimeZone': 'UTC'},
                 'End': {'DateTime': '2026-06-17T09:30:00', 'TimeZone': 'UTC'},
                 'Location': {'DisplayName': ''}, 'Categories': [],
                 'ShowAs': 'Busy', 'IsAllDay': False},
            ]},
        )
        state = _make_state()
        state._search = 'budget'
        fetch_items(state)
        assert len(state.items) == 1
        assert 'Budget' in state.items[0]['subject']

    def test_owa_error_caught(self, monkeypatch):
        from owa_cal import api as api_mod
        from owa_core.errors import OwaError
        monkeypatch.setattr(api_mod, 'api_get', lambda *a, **kw: (_ for _ in ()).throw(OwaError('boom')))
        state = _make_state()
        fetch_items(state)  # must not raise
        assert 'error' in state.status.lower() or state.status != ''


# ---------------------------------------------------------------------------
# on_search / on_refresh
# ---------------------------------------------------------------------------

class TestOnSearch:
    def test_sets_search_and_dirty(self):
        state = _make_state()
        state.dirty = False
        on_search(state, 'standup')
        assert state._search == 'standup'
        assert state.dirty is True

    def test_empty_search_clears(self):
        state = _make_state()
        state._search = 'old'
        on_search(state, '')
        assert state._search == ''
        assert state.dirty is True


class TestOnRefresh:
    def test_sets_dirty(self):
        state = _make_state()
        state.dirty = False
        on_refresh(state)
        assert state.dirty is True


# ---------------------------------------------------------------------------
# on_drill / on_back
# ---------------------------------------------------------------------------

class TestOnDrill:
    def test_focuses_detail(self):
        state = _make_state([_make_event()])
        state.focus = 'list'
        on_drill(state, state.items[0])
        assert state.focus == 'detail'


class TestOnBack:
    def test_returns_false_no_stack(self):
        state = _make_state()
        result = on_back(state)
        assert result is False


# ---------------------------------------------------------------------------
# _do_respond (respond action)
# ---------------------------------------------------------------------------

class TestDoRespond:
    """`_do_respond(state, action)` sends directly — the y+a/t/d chord already
    confirmed intent, so there is no stdscr / no y/N prompt."""

    def test_respond_accept_sends(self, monkeypatch):
        from owa_cal import api as api_mod
        called = []
        monkeypatch.setattr(
            api_mod, 'api_request',
            lambda method, base, endpoint, token, body=None, debug=False:
                called.append(endpoint) or {},
        )
        state = _make_state([_make_event()])
        state.selected = 0
        _do_respond(state, 'accept')
        assert len(called) == 1
        assert 'accept' in called[0]
        assert state.dirty is True

    def test_respond_no_event_selected(self):
        state = _make_state([])
        state.selected = 0
        _do_respond(state, 'accept')
        assert state.status == 'no event selected'

    def test_respond_api_failure(self, monkeypatch):
        from owa_cal import api as api_mod
        monkeypatch.setattr(api_mod, 'api_request', lambda *a, **kw: None)
        state = _make_state([_make_event()])
        state.selected = 0
        _do_respond(state, 'tentative')
        assert 'failed' in state.status

    def test_respond_tentative_uses_tentativelyaccept(self, monkeypatch):
        from owa_cal import api as api_mod
        called = []
        monkeypatch.setattr(
            api_mod, 'api_request',
            lambda method, base, endpoint, token, body=None, debug=False:
                called.append(endpoint) or {},
        )
        state = _make_state([_make_event()])
        state.selected = 0
        _do_respond(state, 'tentative')
        assert called
        assert 'tentativelyaccept' in called[0]

    def test_respond_event_no_id(self):
        state = _make_state([_make_event(id='')])
        state.selected = 0
        _do_respond(state, 'accept')
        assert state.status == 'event has no id'
