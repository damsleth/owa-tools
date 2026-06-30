"""owa-people API wrapper tests."""
import pytest

from owa_core.errors import (
    AuthExpiredError,
    NetworkError,
    NotFoundError,
    ScopeInsufficientError,
)
from owa_core.http import Response
from owa_people import api


def test_api_request_returns_core_http_json(monkeypatch):
    seen = {}

    def fake_request(method, url, **kwargs):
        seen['method'] = method
        seen['url'] = url
        seen['kwargs'] = kwargs
        return Response(status=200, headers={}, json={'ok': True}, bytes=b'{}')

    monkeypatch.setattr(api.http, 'request', fake_request)
    out = api.api_request(
        'GET',
        'https://graph.microsoft.com/v1.0',
        '/me',
        'fake-token',
        extra_headers={'ConsistencyLevel': 'eventual'},
    )
    assert out == {'ok': True}
    assert seen['method'] == 'GET'
    assert seen['url'] == 'https://graph.microsoft.com/v1.0/me'
    assert seen['kwargs']['token'] == 'fake-token'
    assert seen['kwargs']['headers'] == {'ConsistencyLevel': 'eventual'}


def test_api_request_not_found_raises(monkeypatch):
    def fake_request(method, url, **kwargs):
        raise NotFoundError('not found (404)')

    monkeypatch.setattr(api.http, 'request', fake_request)
    with pytest.raises(NotFoundError):
        api.api_request('GET', 'https://graph.microsoft.com/v1.0', '/missing', 'fake')


def test_api_request_auth_failure_raises_typed_error(monkeypatch):
    def fake_request(method, url, **kwargs):
        raise AuthExpiredError('auth expired (401)')

    monkeypatch.setattr(api.http, 'request', fake_request)
    with pytest.raises(AuthExpiredError) as exc:
        api.api_request('GET', 'https://graph.microsoft.com/v1.0', '/me', 'fake')
    assert exc.value.exit_code == 11


def test_api_get_binary_returns_bytes(monkeypatch):
    seen = {}

    def fake_request(method, url, **kwargs):
        seen['url'] = url
        seen['raw'] = kwargs.get('raw')
        return Response(status=200, headers={}, json=None, bytes=b'\xff\xd8jpeg')

    monkeypatch.setattr(api.http, 'request', fake_request)
    out = api.api_get_binary(
        'https://graph.microsoft.com/v1.0', 'me/photo/$value', 'fake-token',
    )
    assert out == b'\xff\xd8jpeg'
    assert seen['url'] == 'https://graph.microsoft.com/v1.0/me/photo/$value'
    assert seen['raw'] is True


def test_api_get_binary_scope_error_raises(monkeypatch):
    def fake_request(method, url, **kwargs):
        raise ScopeInsufficientError('access denied (403)')

    monkeypatch.setattr(api.http, 'request', fake_request)
    with pytest.raises(ScopeInsufficientError):
        api.api_get_binary('https://graph.microsoft.com/v1.0', 'me/photo/$value', 'fake')


def test_api_get_binary_network_error_raises(monkeypatch):
    def fake_request(method, url, **kwargs):
        raise NetworkError('network error: boom')

    monkeypatch.setattr(api.http, 'request', fake_request)
    with pytest.raises(NetworkError):
        api.api_get_binary('https://graph.microsoft.com/v1.0', 'me/photo/$value', 'fake')
