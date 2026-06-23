"""Tests for owa_planner.api (Graph HTTP helper). No network."""
import pytest

from owa_core import errors
from owa_core.http import Response
from owa_planner import api as api_mod


def _resp(json_obj):
    return Response(status=200, headers={}, json=json_obj, bytes=b'')


def test_api_get_returns_json(monkeypatch):
    monkeypatch.setattr(
        api_mod.http, 'request', lambda method, url, **k: _resp({'value': [1, 2]})
    )
    assert api_mod.api_get('https://g', 'me/planner/plans', 'tok') == {'value': [1, 2]}


def test_api_request_recoverable_raises(monkeypatch):
    def boom(*a, **k):
        raise errors.NotFoundError('not found (404)')

    monkeypatch.setattr(api_mod.http, 'request', boom)
    with pytest.raises(errors.NotFoundError):
        api_mod.api_get('https://g', 'planner/tasks/x', 'tok')


def test_api_request_auth_reraises(monkeypatch):
    def boom(*a, **k):
        raise errors.AuthExpiredError('auth expired (401)')

    monkeypatch.setattr(api_mod.http, 'request', boom)
    with pytest.raises(errors.AuthExpiredError):
        api_mod.api_get('https://g', 'me/planner/plans', 'tok')


def test_api_request_scope_reraises(monkeypatch):
    def boom(*a, **k):
        raise errors.ScopeInsufficientError('access denied (403)')

    monkeypatch.setattr(api_mod.http, 'request', boom)
    with pytest.raises(errors.ScopeInsufficientError):
        api_mod.api_get('https://g', 'me/planner/plans', 'tok')


def test_paginate_all(monkeypatch):
    monkeypatch.setattr(
        api_mod.http, 'paginate', lambda url, **k: iter([{'id': 'a'}, {'id': 'b'}])
    )
    assert api_mod.paginate_all('https://g', 'me/planner/plans', 'tok') == [
        {'id': 'a'}, {'id': 'b'},
    ]


def test_paginate_all_recoverable_raises(monkeypatch):
    def boom(url, **k):
        raise errors.NetworkError('service unavailable (503)')

    monkeypatch.setattr(api_mod.http, 'paginate', boom)
    with pytest.raises(errors.NetworkError):
        api_mod.paginate_all('https://g', 'me/planner/plans', 'tok')


def test_api_request_generic_owaerror_raises(monkeypatch):
    def boom(*a, **k):
        raise errors.OwaError('weird')

    monkeypatch.setattr(api_mod.http, 'request', boom)
    with pytest.raises(errors.OwaError):
        api_mod.api_get('https://g', 'me/planner/plans', 'tok')


def test_paginate_all_generic_owaerror_raises(monkeypatch):
    def boom(url, **k):
        raise errors.OwaError('weird')

    monkeypatch.setattr(api_mod.http, 'paginate', boom)
    with pytest.raises(errors.OwaError):
        api_mod.paginate_all('https://g', 'me/planner/plans', 'tok')


def test_build_query():
    assert api_mod.build_query({'$top': 5}) == '$top=5'
    assert api_mod.build_query({'$select': 'a,b'}) == '$select=a%2Cb'
