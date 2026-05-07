"""Format tests."""
from owa_drive.format import _human_size, format_items_pretty


def test_human_size_thresholds():
    assert _human_size(0) == '0B'
    assert _human_size(1023) == '1023B'
    assert _human_size(1024) == '1.0K'
    assert _human_size(1024 * 1024) == '1.0M'
    assert _human_size(None) == '-'
    assert _human_size('abc') == '-'


def test_format_items_pretty_empty():
    assert format_items_pretty([]) == '(empty)'


def test_format_items_pretty_renders_columns():
    items = [
        {'kind': 'folder', 'size': None, 'lastModified': '2026-05-04T12:00:00Z',
         'name': 'Documents'},
        {'kind': 'file', 'size': 1234, 'lastModified': '2026-05-04T12:30:00Z',
         'name': 'foo.txt'},
    ]
    out = format_items_pretty(items)
    assert 'Documents' in out
    assert 'foo.txt' in out
    assert '\n' in out
