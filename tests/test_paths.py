"""Pure-function tests for paths.py.

These pin the exact Graph endpoint shape; behavior changes here
ripple to every cmd_* in cli.py.
"""
import pytest

from owa_drive.paths import (
    children_endpoint,
    content_endpoint,
    delete_endpoint,
    item_endpoint,
    normalize_path,
)


def test_normalize_path_strips_slashes():
    assert normalize_path('/Documents/foo.txt/') == 'Documents/foo.txt'


def test_normalize_path_root_variants():
    assert normalize_path('') == ''
    assert normalize_path('/') == ''
    assert normalize_path('.') == ''
    assert normalize_path(None) == ''


def test_normalize_path_preserves_inner_spaces():
    assert normalize_path('/Documents/Q1 plan.docx') == 'Documents/Q1 plan.docx'


def test_item_endpoint_root():
    assert item_endpoint('') == 'me/drive/root'
    assert item_endpoint('/') == 'me/drive/root'


def test_item_endpoint_path():
    assert item_endpoint('/Documents/foo.txt') == 'me/drive/root:/Documents/foo.txt:'


def test_item_endpoint_quotes_special_chars():
    # spaces -> %20, etc.
    out = item_endpoint('/Documents/Q1 plan.docx')
    assert out == 'me/drive/root:/Documents/Q1%20plan.docx:'


def test_children_endpoint_root():
    assert children_endpoint('') == 'me/drive/root/children'


def test_children_endpoint_path():
    assert children_endpoint('/Documents') == 'me/drive/root:/Documents:/children'


def test_content_endpoint_root_raises():
    with pytest.raises(ValueError):
        content_endpoint('')


def test_content_endpoint_path():
    assert content_endpoint('/Documents/foo.txt') == 'me/drive/root:/Documents/foo.txt:/content'


def test_delete_endpoint_root_raises():
    with pytest.raises(ValueError):
        delete_endpoint('/')


def test_delete_endpoint_path():
    # Note: no trailing colon for the metadata-style URL
    assert delete_endpoint('/Documents/foo.txt') == 'me/drive/root:/Documents/foo.txt'
