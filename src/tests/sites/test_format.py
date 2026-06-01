"""Tests for owa_sites.format (--pretty rendering)."""

from owa_sites import format as fmt


def test_format_web_pretty():
    assert 'not found' in fmt.format_web_pretty({}).lower()
    out = fmt.format_web_pretty({'title': 'T', 'url': 'u', 'created': 'c'})
    assert out.splitlines()[0] == 'T'
    assert 'url: u' in out
    assert 'created: c' in out


def test_format_lists_pretty():
    assert 'No lists' in fmt.format_lists_pretty([])
    out = fmt.format_lists_pretty([{'title': 'Documents', 'itemCount': 5, 'id': 'l1'}])
    assert 'Documents' in out and '5' in out and 'l1' in out


def test_format_lists_pretty_unknown_count():
    out = fmt.format_lists_pretty([{'title': 'X', 'itemCount': None, 'id': 'l1'}])
    assert '?' in out


def test_format_files_pretty():
    assert 'No files' in fmt.format_files_pretty([])
    out = fmt.format_files_pretty([{'name': 'a.docx', 'length': 10, 'modified': 't'}])
    assert 'a.docx' in out


def test_format_items_pretty():
    assert 'No items' in fmt.format_items_pretty([])
    assert 'Hello' in fmt.format_items_pretty([{'Title': 'Hello'}])
    assert 'leaf.docx' in fmt.format_items_pretty([{'FileLeafRef': 'leaf.docx'}])


def test_format_search_pretty():
    assert 'No results' in fmt.format_search_pretty([])
    out = fmt.format_search_pretty([{'Title': 'Doc', 'Path': 'http://x'}])
    assert 'Doc' in out and 'http://x' in out
