"""owa-cal API wrapper tests."""
import pytest

from owa_cal import api
from owa_core.errors import AuthExpiredError, NotFoundError
from owa_core.http import Response


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
        'https://outlook.office.com/api/v2.0',
        'me/events',
        'fake-token',
    )
    assert out == {'ok': True}
    assert seen['method'] == 'GET'
    assert seen['url'] == 'https://outlook.office.com/api/v2.0/me/events'
    assert seen['kwargs']['token'] == 'fake-token'


def test_api_request_not_found_raises(monkeypatch):
    def fake_request(method, url, **kwargs):
        raise NotFoundError('not found (404)')

    monkeypatch.setattr(api.http, 'request', fake_request)
    with pytest.raises(NotFoundError):
        api.api_request('GET', 'https://outlook.office.com/api/v2.0', 'missing', 'fake')


def test_api_request_auth_failure_raises_typed_error(monkeypatch):
    def fake_request(method, url, **kwargs):
        raise AuthExpiredError('auth expired (401)')

    monkeypatch.setattr(api.http, 'request', fake_request)
    with pytest.raises(AuthExpiredError) as exc:
        api.api_request('GET', 'https://outlook.office.com/api/v2.0', 'me', 'fake')
    assert exc.value.exit_code == 11
