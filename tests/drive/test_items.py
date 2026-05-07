"""Pure-function tests for items.normalize_item."""
from owa_drive.items import normalize_item


def test_normalize_file():
    upstream = {
        'id': 'abc',
        'name': 'foo.txt',
        'size': 123,
        'lastModifiedDateTime': '2026-05-04T12:00:00Z',
        'webUrl': 'https://...',
        'file': {'mimeType': 'text/plain'},
        'parentReference': {'path': '/drive/root:/Documents'},
    }
    out = normalize_item(upstream)
    assert out['kind'] == 'file'
    assert out['name'] == 'foo.txt'
    assert out['size'] == 123
    assert out['mimeType'] == 'text/plain'
    assert out['parentPath'] == '/Documents'
    assert out['childCount'] is None


def test_normalize_folder():
    upstream = {
        'id': 'def',
        'name': 'Documents',
        'lastModifiedDateTime': '2026-05-04T12:00:00Z',
        'folder': {'childCount': 5},
        'parentReference': {'path': '/drive/root:'},
    }
    out = normalize_item(upstream)
    assert out['kind'] == 'folder'
    assert out['childCount'] == 5
    assert out['mimeType'] == ''
    # Root parent prefix-only -> '/'
    assert out['parentPath'] == '/'


def test_normalize_unknown_kind():
    upstream = {'id': 'x', 'name': 'mystery'}
    out = normalize_item(upstream)
    assert out['kind'] == 'unknown'
    assert out['size'] is None
