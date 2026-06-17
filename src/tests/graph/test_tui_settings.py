"""Tests for owa-graph TUI settings (Phase 1, Agent A2).

Mirrors the mail settings tests: cycle wraps, from_config falls back on bad
values and coerces split_ratio, to_config_dict round-trips, and the bookmarks
helpers tolerate junk while persisting only (audience, path, label).
"""
from __future__ import annotations

from owa_graph import tui_settings as ts


def test_defaults():
    s = ts.DEFAULTS
    assert s.reading_pane == 'right'
    assert s.split_ratio == 50
    assert s.pretty_json == 'on'
    assert s.scope_warnings == 'on'
    assert s.default_audience == 'graph'
    assert s.bookmarks == '[]'


def test_cycle_wraps_enum():
    s = ts.DEFAULTS
    s = ts.cycle(s, 'reading_pane')
    assert s.reading_pane == 'bottom'
    s = ts.cycle(s, 'reading_pane')
    assert s.reading_pane == 'off'
    s = ts.cycle(s, 'reading_pane')
    assert s.reading_pane == 'right'  # wrapped


def test_cycle_toggle():
    s = ts.cycle(ts.DEFAULTS, 'pretty_json')
    assert s.pretty_json == 'off'


def test_cycle_free_text_is_noop():
    s = ts.DEFAULTS
    assert ts.cycle(s, 'default_path') is s


def test_from_config_coerces_and_falls_back():
    cfg = {
        'graph_tui_reading_pane': 'bottom',
        'graph_tui_split_ratio': '60',
        'graph_tui_pretty_json': 'nonsense',  # invalid -> default
        'graph_tui_default_audience': 'azure',
    }
    s = ts.from_config(cfg)
    assert s.reading_pane == 'bottom'
    assert s.split_ratio == 60          # coerced str -> int
    assert s.pretty_json == 'on'        # invalid value fell back to default
    assert s.default_audience == 'azure'


def test_from_config_bad_split_ratio_falls_back():
    s = ts.from_config({'graph_tui_split_ratio': 'not-an-int'})
    assert s.split_ratio == 50


def test_to_config_dict_round_trips():
    s = ts.from_config(ts.to_config_dict(ts.Settings(split_ratio=40, pretty_json='off')))
    assert s.split_ratio == 40
    assert s.pretty_json == 'off'


def test_to_config_dict_keys_match_allowed():
    keys = set(ts.to_config_dict(ts.DEFAULTS))
    assert keys == set(ts._FIELD_TO_KEY.values())


def test_bookmarks_round_trip_and_trims():
    raw = ts.dump_bookmarks([
        {'audience': 'graph', 'path': 'me', 'label': 'Me', 'body': 'SECRET'},
        {'audience': 'azure', 'path': 'subscriptions'},
    ])
    marks = ts.parse_bookmarks(raw)
    assert marks == [
        {'audience': 'graph', 'path': 'me', 'label': 'Me'},
        {'audience': 'azure', 'path': 'subscriptions', 'label': ''},
    ]
    # response bodies must never be persisted
    assert 'SECRET' not in raw


def test_parse_bookmarks_tolerates_junk():
    assert ts.parse_bookmarks('not json') == []
    assert ts.parse_bookmarks('{"not": "a list"}') == []
    assert ts.parse_bookmarks('[1, 2, {"audience": "graph", "path": "me"}]') == [
        {'audience': 'graph', 'path': 'me'},
    ]
