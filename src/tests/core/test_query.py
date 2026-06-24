"""Tests for owa_core.query.build_query."""
import pytest

from owa_core.query import build_query


def test_build_query_single_param():
    assert build_query({'$top': 10}) == '$top=10'


def test_build_query_multiple_params():
    result = build_query({'$top': 5, '$select': 'id,name'})
    assert '$top=5' in result
    assert '$select=id%2Cname' in result


def test_build_query_url_encodes_special_chars():
    out = build_query({'$filter': "startswith(name,'A')"})
    assert out == "$filter=startswith%28name%2C%27A%27%29"


def test_build_query_spaces_encoded():
    out = build_query({'$filter': "Status eq 'Completed'"})
    assert '%20' in out
    assert '%27' in out


def test_build_query_empty_dict():
    assert build_query({}) == ''


def test_require_value_returns_head_and_tail():
    from owa_core.errors import _require_value
    val, rest = _require_value('--foo', ['bar', 'baz'])
    assert val == 'bar'
    assert rest == ['baz']


def test_require_value_raises_usage_error_on_empty():
    from owa_core.errors import UsageError, _require_value
    with pytest.raises(UsageError, match='--x requires a value'):
        _require_value('--x', [])
