"""Tests for owa_mail.tui_settings — Settings model + persistence."""
import pytest

from owa_mail.tui_settings import (
    DATE_FORMAT_VALUES,
    DEFAULTS,
    READING_PANE_VALUES,
    SORT_BY_VALUES,
    SPLIT_RATIO_VALUES,
    Settings,
    cycle,
    from_config,
    to_config_dict,
)

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------


def test_defaults_reading_pane():
    assert DEFAULTS.reading_pane == 'right'


def test_defaults_split_ratio():
    assert DEFAULTS.split_ratio == 50


def test_defaults_sort_by():
    assert DEFAULTS.sort_by == 'date_desc'


def test_defaults_date_format():
    assert DEFAULTS.date_format == 'iso8601'


def test_defaults_date_custom():
    assert DEFAULTS.date_custom == ''


def test_settings_is_frozen():
    from dataclasses import FrozenInstanceError

    s = Settings()
    with pytest.raises(FrozenInstanceError):
        s.reading_pane = 'bottom'  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Round-trip: from_config(to_config_dict(s)) == s
# ---------------------------------------------------------------------------


def test_roundtrip_defaults():
    s = Settings()
    assert from_config(to_config_dict(s)) == s


def test_roundtrip_all_non_default():
    s = Settings(
        reading_pane='bottom',
        split_ratio=40,
        sort_by='sender',
        date_format='ddmm',
        date_custom='%d/%m',
    )
    assert from_config(to_config_dict(s)) == s


def test_roundtrip_off_pane():
    s = Settings(reading_pane='off', split_ratio=60, sort_by='unread_first')
    assert from_config(to_config_dict(s)) == s


def test_to_config_dict_all_values_are_strings():
    d = to_config_dict(Settings())
    for k, v in d.items():
        assert isinstance(k, str), f'key {k!r} is not a str'
        assert isinstance(v, str), f'value for {k!r} is not a str'


def test_to_config_dict_keys_match_allowed_keys():
    from owa_mail.config import ALLOWED_KEYS

    d = to_config_dict(Settings())
    tui_keys = {k for k in ALLOWED_KEYS if k.startswith('tui_')}
    assert tui_keys == set(d.keys())


# ---------------------------------------------------------------------------
# from_config: empty / missing config
# ---------------------------------------------------------------------------


def test_from_config_empty_dict_gives_defaults():
    assert from_config({}) == DEFAULTS


def test_from_config_unrelated_keys_ignored():
    cfg = {'owa_piggy_profile': 'work', 'debug': '1'}
    assert from_config(cfg) == DEFAULTS


# ---------------------------------------------------------------------------
# from_config: invalid stored values fall back to default
# ---------------------------------------------------------------------------


def test_from_config_invalid_reading_pane_falls_back():
    s = from_config({'tui_reading_pane': 'diagonal'})
    assert s.reading_pane == DEFAULTS.reading_pane


def test_from_config_invalid_split_ratio_string_falls_back():
    s = from_config({'tui_split_ratio': 'half'})
    assert s.split_ratio == DEFAULTS.split_ratio


def test_from_config_out_of_range_split_ratio_falls_back():
    s = from_config({'tui_split_ratio': '99'})
    assert s.split_ratio == DEFAULTS.split_ratio


def test_from_config_invalid_sort_by_falls_back():
    s = from_config({'tui_sort_by': 'magic'})
    assert s.sort_by == DEFAULTS.sort_by


def test_from_config_invalid_date_format_falls_back():
    s = from_config({'tui_date_format': 'rfc2822'})
    assert s.date_format == DEFAULTS.date_format


def test_from_config_valid_split_ratio_int_as_string():
    s = from_config({'tui_split_ratio': '40'})
    assert s.split_ratio == 40
    assert isinstance(s.split_ratio, int)


# ---------------------------------------------------------------------------
# from_config: date_custom is free-text (any string accepted)
# ---------------------------------------------------------------------------


def test_from_config_date_custom_any_string():
    s = from_config({'tui_date_custom': '%A %d %B %Y'})
    assert s.date_custom == '%A %d %B %Y'


def test_from_config_date_custom_empty_string():
    s = from_config({'tui_date_custom': ''})
    # Empty string stored as empty; parse_lines in owa_core.config strips
    # empty values but from_config should handle absent key -> default('')
    assert s.date_custom == DEFAULTS.date_custom


# ---------------------------------------------------------------------------
# cycle() — wraps for each enum field
# ---------------------------------------------------------------------------


def test_cycle_reading_pane_advances():
    s = Settings(reading_pane='right')
    s2 = cycle(s, 'reading_pane')
    assert s2.reading_pane == 'bottom'


def test_cycle_reading_pane_wraps():
    s = Settings(reading_pane='off')
    s2 = cycle(s, 'reading_pane')
    assert s2.reading_pane == 'right'  # wraps back to first


def test_cycle_reading_pane_all_values():
    s = Settings(reading_pane='right')
    visited = []
    for _ in range(len(READING_PANE_VALUES)):
        visited.append(s.reading_pane)
        s = cycle(s, 'reading_pane')
    assert set(visited) == set(READING_PANE_VALUES)
    # Full cycle returns to start
    assert s.reading_pane == 'right'


def test_cycle_split_ratio_advances():
    s = Settings(split_ratio=40)
    s2 = cycle(s, 'split_ratio')
    assert s2.split_ratio == 50


def test_cycle_split_ratio_wraps():
    s = Settings(split_ratio=60)
    s2 = cycle(s, 'split_ratio')
    assert s2.split_ratio == 40  # wraps


def test_cycle_split_ratio_all_values():
    s = Settings(split_ratio=SPLIT_RATIO_VALUES[0])
    visited = []
    for _ in range(len(SPLIT_RATIO_VALUES)):
        visited.append(s.split_ratio)
        s = cycle(s, 'split_ratio')
    assert set(visited) == set(SPLIT_RATIO_VALUES)
    assert s.split_ratio == SPLIT_RATIO_VALUES[0]


def test_cycle_sort_by_advances():
    s = Settings(sort_by='date_desc')
    s2 = cycle(s, 'sort_by')
    assert s2.sort_by == 'date_asc'


def test_cycle_sort_by_wraps():
    s = Settings(sort_by=SORT_BY_VALUES[-1])
    s2 = cycle(s, 'sort_by')
    assert s2.sort_by == SORT_BY_VALUES[0]


def test_cycle_sort_by_all_values():
    s = Settings(sort_by=SORT_BY_VALUES[0])
    visited = []
    for _ in range(len(SORT_BY_VALUES)):
        visited.append(s.sort_by)
        s = cycle(s, 'sort_by')
    assert set(visited) == set(SORT_BY_VALUES)
    assert s.sort_by == SORT_BY_VALUES[0]


def test_cycle_date_format_advances():
    s = Settings(date_format='iso8601')
    s2 = cycle(s, 'date_format')
    assert s2.date_format == 'ddmm'


def test_cycle_date_format_wraps():
    s = Settings(date_format=DATE_FORMAT_VALUES[-1])
    s2 = cycle(s, 'date_format')
    assert s2.date_format == DATE_FORMAT_VALUES[0]


def test_cycle_date_format_all_values():
    s = Settings(date_format=DATE_FORMAT_VALUES[0])
    visited = []
    for _ in range(len(DATE_FORMAT_VALUES)):
        visited.append(s.date_format)
        s = cycle(s, 'date_format')
    assert set(visited) == set(DATE_FORMAT_VALUES)
    assert s.date_format == DATE_FORMAT_VALUES[0]


def test_cycle_date_custom_is_noop():
    s = Settings(date_custom='%Y/%m/%d')
    s2 = cycle(s, 'date_custom')
    assert s2 is s  # unchanged


def test_cycle_unknown_field_raises():
    s = Settings()
    with pytest.raises(ValueError):
        cycle(s, 'nonexistent_field')


def test_cycle_does_not_mutate_original():
    s = Settings(reading_pane='right')
    _ = cycle(s, 'reading_pane')
    assert s.reading_pane == 'right'  # original unchanged


# ---------------------------------------------------------------------------
# config.py accepts the new keys
# ---------------------------------------------------------------------------


def test_config_py_allows_tui_reading_pane():
    from owa_mail.config import ALLOWED_KEYS

    assert 'tui_reading_pane' in ALLOWED_KEYS


def test_config_py_allows_tui_split_ratio():
    from owa_mail.config import ALLOWED_KEYS

    assert 'tui_split_ratio' in ALLOWED_KEYS


def test_config_py_allows_tui_sort_by():
    from owa_mail.config import ALLOWED_KEYS

    assert 'tui_sort_by' in ALLOWED_KEYS


def test_config_py_allows_tui_date_format():
    from owa_mail.config import ALLOWED_KEYS

    assert 'tui_date_format' in ALLOWED_KEYS


def test_config_py_allows_tui_date_custom():
    from owa_mail.config import ALLOWED_KEYS

    assert 'tui_date_custom' in ALLOWED_KEYS


def test_config_set_accepts_tui_keys(tmp_config, clean_env):
    """config_set should accept all five TUI keys without raising."""
    from owa_mail.config import config_set

    config_set('tui_reading_pane', 'bottom')
    config_set('tui_split_ratio', '40')
    config_set('tui_sort_by', 'sender')
    config_set('tui_date_format', 'ddmm')
    config_set('tui_date_custom', '%d/%m')


def test_config_set_tui_key_persisted(tmp_config, clean_env):
    from owa_mail.config import config_set, load_config

    config_set('tui_reading_pane', 'off')
    cfg = load_config()
    assert cfg.get('tui_reading_pane') == 'off'


def test_parse_kv_stream_accepts_tui_keys():
    from owa_mail.config import parse_kv_stream

    text = (
        'tui_reading_pane="right"\n'
        'tui_split_ratio="50"\n'
        'tui_sort_by="date_desc"\n'
        'tui_date_format="iso8601"\n'
        'tui_date_custom=""\n'
    )
    out = parse_kv_stream(text)
    assert out.get('tui_reading_pane') == 'right'
    assert out.get('tui_split_ratio') == '50'
    assert out.get('tui_sort_by') == 'date_desc'
    assert out.get('tui_date_format') == 'iso8601'
