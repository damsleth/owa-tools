"""Tests for shared pretty-format helpers."""
from owa_core import format as fmt


def test_pad_handles_none_short_and_long_values():
    assert fmt.pad(None, 3) == '   '
    assert fmt.pad('ab', 4) == 'ab  '
    assert fmt.pad('abcd', 2) == 'abcd'


def test_truncate_handles_none_suffix_and_tiny_widths():
    assert fmt.truncate(None, 3) == ''
    assert fmt.truncate('abcdef', 4) == 'abc…'
    assert fmt.truncate('abcdef', 1) == '…'
    assert fmt.truncate('abcdef', 2, suffix='..') == '..'
    assert fmt.truncate('abc', 3) == 'abc'


def test_date_and_time_parts():
    assert fmt.date_part('2026-05-08T12:34:56') == '2026-05-08'
    assert fmt.date_part('') == ''
    assert fmt.time_part('2026-05-08T12:34:56') == '12:34'
    assert fmt.time_part('2026-05-08') == ''
    assert fmt.time_part(None) == ''
