"""owa-todo API wrapper tests."""
import pytest

from owa_core.errors import AuthExpiredError, NotFoundError
from owa_core.http import Response
from owa_todo import api


def test_build_query_encodes_values():
    assert api.build_query({'$top': 50}) == '$top=50'
    out = api.build_query({'$filter': "Status eq 'Completed'"})
    assert out.startswith('$filter=') and '%20' in out and "%27" in out


def test_api_request_returns_core_http_json(monkeypatch):
    seen = {}

    def fake_request(method, url, **kwargs):
        seen['method'] = method
        seen['url'] = url
        seen['kwargs'] = kwargs
        return Response(status=200, headers={}, json={'ok': True}, bytes=b'{}')

    monkeypatch.setattr(api.http, 'request', fake_request)
    out = api.api_request('GET', 'https://outlook.test', 'me/tasks', 'fake-token')
    assert out == {'ok': True}
    assert seen['url'] == 'https://outlook.test/me/tasks'
    assert seen['kwargs']['token'] == 'fake-token'


def test_api_request_not_found_raises(monkeypatch):
    monkeypatch.setattr(api.http, 'request', lambda *a, **k: (_ for _ in ()).throw(NotFoundError('not found (404)')))
    with pytest.raises(NotFoundError):
        api.api_request('GET', 'https://outlook.test', 'missing', 'fake')


def test_api_request_auth_failure_reraises(monkeypatch):
    monkeypatch.setattr(api.http, 'request', lambda *a, **k: (_ for _ in ()).throw(AuthExpiredError('auth expired (401)')))
    with pytest.raises(AuthExpiredError) as exc:
        api.api_request('GET', 'https://outlook.test', 'me', 'fake')
    assert exc.value.exit_code == 11


def test_paginate_all_collects_items(monkeypatch):
    monkeypatch.setattr(api.http, 'paginate', lambda url, **k: iter([{'Id': '1'}, {'Id': '2'}]))
    out = api.paginate_all('https://outlook.test', 'me/tasks', 'fake')
    assert [i['Id'] for i in out] == ['1', '2']


def test_paginate_all_recoverable_error_raises(monkeypatch):
    def boom(url, **k):
        raise NotFoundError('not found (404)')

    monkeypatch.setattr(api.http, 'paginate', boom)
    with pytest.raises(NotFoundError):
        api.paginate_all('https://outlook.test', 'me/tasks', 'fake')
