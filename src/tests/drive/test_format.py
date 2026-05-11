"""Format tests."""
from owa_drive.format import _human_size, format_item_pretty, format_items_pretty


def test_human_size_thresholds():
    assert _human_size(0) == '0B'
    assert _human_size(1023) == '1023B'
    assert _human_size(1024) == '1.0K'
    assert _human_size(1024 * 1024) == '1.0M'
    assert _human_size(None) == '-'
    assert _human_size('abc') == '-'
    assert _human_size(1024 * 1024 * 1024) == '1.0G'
    assert _human_size(1024 * 1024 * 1024 * 1024) == '1.0T'


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


def test_format_items_pretty_truncates_long_names():
    out = format_items_pretty([
        {'kind': 'file', 'size': 10, 'lastModified': '', 'name': 'x' * 100},
    ])
    assert 'x' * 77 + '...' in out


def test_format_item_pretty_empty():
    assert format_item_pretty(None) == '(no item)'


def test_format_item_pretty_full_record():
    out = format_item_pretty({
        'name': 'report.docx',
        'kind': 'file',
        'size': '2048',
        'mimeType': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'lastModified': '2026-05-09T12:00:00Z',
        'parentPath': '/drive/root:/Reports',
        'webUrl': 'https://example.test/report.docx',
        'id': 'item-1',
    })

    assert out.startswith('report.docx [file]')
    assert 'size:     2.0K' in out
    assert 'type:     application/vnd.openxmlformats-officedocument.wordprocessingml.document' in out
    assert 'parent:   /drive/root:/Reports' in out
    assert 'id:       item-1' in out


def test_format_item_pretty_fallback_name():
    assert format_item_pretty({'kind': 'folder'}) == '(no name) [folder]'
