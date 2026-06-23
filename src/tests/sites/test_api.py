"""Tests for owa_sites.api (SharePoint REST HTTP helper). No network."""
import pytest

from owa_core import errors
from owa_core.http import Response
from owa_sites import api as api_mod


def _resp(json_obj):
    return Response(status=200, headers={}, json=json_obj, bytes=b'')


def test_sp_get_sends_nometadata_accept(monkeypatch):
    seen = {}

    def fake_request(method, url, **k):
        seen['headers'] = k.get('headers')
        return _resp({'Title': 'X'})

    monkeypatch.setattr(api_mod.http, 'request', fake_request)
    assert api_mod.sp_get('https://h', 'sites/x/_api/web', 'tok') == {'Title': 'X'}
    assert seen['headers']['Accept'] == api_mod.ACCEPT_JSON


def test_sp_request_recoverable_raises(monkeypatch):
    def boom(*a, **k):
        raise errors.NotFoundError('not found (404)')

    monkeypatch.setattr(api_mod.http, 'request', boom)
    with pytest.raises(errors.NotFoundError):
        api_mod.sp_get('https://h', 'sites/x/_api/web', 'tok')


def test_sp_request_auth_reraises(monkeypatch):
    def boom(*a, **k):
        raise errors.ScopeInsufficientError('access denied (403)')

    monkeypatch.setattr(api_mod.http, 'request', boom)
    with pytest.raises(errors.ScopeInsufficientError):
        api_mod.sp_get('https://h', 'sites/x/_api/web', 'tok')


def test_sp_request_generic_owaerror_raises(monkeypatch):
    def boom(*a, **k):
        raise errors.OwaError('weird')

    monkeypatch.setattr(api_mod.http, 'request', boom)
    with pytest.raises(errors.OwaError):
        api_mod.sp_get('https://h', 'sites/x/_api/web', 'tok')


def test_paginate_sp_follows_nextlink(monkeypatch):
    calls = []

    def fake_request(method, url, **k):
        calls.append(url)
        if len(calls) == 1:
            return _resp({'value': [{'a': 1}], 'odata.nextLink': 'https://h/next'})
        return _resp({'value': [{'a': 2}]})

    monkeypatch.setattr(api_mod.http, 'request', fake_request)
    out = api_mod.paginate_sp('https://h', 'sites/x/_api/web/lists', 'tok')
    assert out == [{'a': 1}, {'a': 2}]
    assert len(calls) == 2


def test_paginate_sp_single_object(monkeypatch):
    monkeypatch.setattr(api_mod.http, 'request', lambda method, url, **k: _resp({'Title': 'X'}))
    assert api_mod.paginate_sp('https://h', 'sites/x/_api/web', 'tok') == [{'Title': 'X'}]


def test_paginate_sp_recoverable_raises(monkeypatch):
    def boom(method, url, **k):
        raise errors.NetworkError('service unavailable (503)')

    monkeypatch.setattr(api_mod.http, 'request', boom)
    with pytest.raises(errors.NetworkError):
        api_mod.paginate_sp('https://h', 'sites/x/_api/web/lists', 'tok')


def test_paginate_sp_auth_reraises(monkeypatch):
    def boom(method, url, **k):
        raise errors.AuthExpiredError('auth expired (401)')

    monkeypatch.setattr(api_mod.http, 'request', boom)
    with pytest.raises(errors.AuthExpiredError):
        api_mod.paginate_sp('https://h', 'sites/x/_api/web/lists', 'tok')
