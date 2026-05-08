"""owa-drive API wrapper tests."""
import pytest

from owa_core.errors import AuthExpiredError, ConflictError
from owa_core.http import Response
from owa_drive import api


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
        '/me/drive/root/children',
        'fake-token',
        extra_headers={'Prefer': 'x'},
    )
    assert out == {'ok': True}
    assert seen['url'] == 'https://graph.microsoft.com/v1.0/me/drive/root/children'
    assert seen['kwargs']['headers'] == {'Prefer': 'x'}


def test_api_get_binary_returns_bytes(monkeypatch):
    def fake_request(method, url, **kwargs):
        assert kwargs['raw'] is True
        return Response(status=200, headers={}, json=None, bytes=b'file')

    monkeypatch.setattr(api.http, 'request', fake_request)
    assert api.api_get_binary('https://graph.microsoft.com/v1.0', '/content', 'fake') == b'file'


def test_api_put_binary_uses_octet_stream(monkeypatch):
    seen = {}

    def fake_request(method, url, **kwargs):
        seen['method'] = method
        seen['body'] = kwargs['body']
        seen['headers'] = kwargs['headers']
        return Response(status=200, headers={}, json={'id': '1'}, bytes=b'{}')

    monkeypatch.setattr(api.http, 'request', fake_request)
    out = api.api_put_binary('https://graph.microsoft.com/v1.0', '/content', 'fake', b'abc')
    assert out == {'id': '1'}
    assert seen == {
        'method': 'PUT',
        'body': b'abc',
        'headers': {'Content-Type': 'application/octet-stream'},
    }


def test_api_put_binary_preserves_size_guard(capsys):
    out = api.api_put_binary(
        'https://graph.microsoft.com/v1.0',
        '/content',
        'fake',
        b'x' * (api.UPLOAD_LIMIT_BYTES + 1),
    )
    assert out is None
    assert 'simple upload path is limited' in capsys.readouterr().err


def test_api_request_conflict_preserves_none_contract(monkeypatch, capsys):
    def fake_request(method, url, **kwargs):
        raise ConflictError('conflict (409)')

    monkeypatch.setattr(api.http, 'request', fake_request)
    assert api.api_request('DELETE', 'https://graph.microsoft.com/v1.0', '/x', 'fake') is None
    assert 'conflict' in capsys.readouterr().err


def test_api_request_auth_failure_raises_typed_error(monkeypatch):
    def fake_request(method, url, **kwargs):
        raise AuthExpiredError('auth expired (401)')

    monkeypatch.setattr(api.http, 'request', fake_request)
    with pytest.raises(AuthExpiredError) as exc:
        api.api_request('GET', 'https://graph.microsoft.com/v1.0', '/me', 'fake')
    assert exc.value.exit_code == 11
