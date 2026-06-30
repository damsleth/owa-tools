"""owa-drive API wrapper tests."""
import pytest

from owa_core.errors import AuthExpiredError, ConflictError, InternalError
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


def test_api_put_binary_preserves_size_guard():
    with pytest.raises(InternalError, match='simple upload path is limited'):
        api.api_put_binary(
            'https://graph.microsoft.com/v1.0',
            '/content',
            'fake',
            b'x' * (api.UPLOAD_LIMIT_BYTES + 1),
        )


def test_api_upload_session_creates_session_and_drives_upload(monkeypatch):
    seen = {}

    def fake_request(method, url, **kwargs):
        seen['method'] = method
        seen['url'] = url
        seen['body'] = kwargs.get('body')
        return Response(
            status=200, headers={},
            json={'uploadUrl': 'https://up.example.test/sess'}, bytes=b'{}',
        )

    def fake_upload_session(upload_url, content, **kwargs):
        seen['upload_url'] = upload_url
        seen['content'] = content
        return {'id': 'big-1', 'name': 'big.bin'}

    monkeypatch.setattr(api.http, 'request', fake_request)
    monkeypatch.setattr(api.upload_mod, 'upload_session', fake_upload_session)

    out = api.api_upload_session(
        'https://graph.microsoft.com/v1.0',
        'me/drive/root:/big.bin:/createUploadSession',
        'fake-token',
        b'x' * 100,
    )
    assert out == {'id': 'big-1', 'name': 'big.bin'}
    assert seen['method'] == 'POST'
    assert seen['url'].endswith('/createUploadSession')
    assert seen['body'] == {'item': {'@microsoft.graph.conflictBehavior': 'replace'}}
    assert seen['upload_url'] == 'https://up.example.test/sess'
    assert seen['content'] == b'x' * 100


def test_api_upload_session_missing_upload_url_raises(monkeypatch):
    def fake_request(method, url, **kwargs):
        return Response(status=200, headers={}, json={}, bytes=b'{}')

    monkeypatch.setattr(api.http, 'request', fake_request)
    with pytest.raises(InternalError, match='uploadUrl'):
        api.api_upload_session(
            'https://graph.microsoft.com/v1.0',
            'me/drive/root:/big.bin:/createUploadSession',
            'fake-token',
            b'x' * 100,
        )


def test_api_upload_session_session_conflict_raises(monkeypatch):
    def fake_request(method, url, **kwargs):
        raise ConflictError('conflict (409)')

    monkeypatch.setattr(api.http, 'request', fake_request)
    with pytest.raises(ConflictError):
        api.api_upload_session(
            'https://graph.microsoft.com/v1.0',
            'me/drive/root:/big.bin:/createUploadSession',
            'fake-token',
            b'x' * 100,
        )


def test_api_upload_session_upload_failure_raises(monkeypatch):
    def fake_request(method, url, **kwargs):
        return Response(
            status=200, headers={},
            json={'uploadUrl': 'https://up.example.test/sess'}, bytes=b'{}',
        )

    def fake_upload_session(upload_url, content, **kwargs):
        raise InternalError('upload chunk failed: HTTP 500')

    monkeypatch.setattr(api.http, 'request', fake_request)
    monkeypatch.setattr(api.upload_mod, 'upload_session', fake_upload_session)
    with pytest.raises(InternalError):
        api.api_upload_session(
            'https://graph.microsoft.com/v1.0',
            'me/drive/root:/big.bin:/createUploadSession',
            'fake-token',
            b'x' * 100,
        )


def test_api_request_conflict_raises(monkeypatch):
    def fake_request(method, url, **kwargs):
        raise ConflictError('conflict (409)')

    monkeypatch.setattr(api.http, 'request', fake_request)
    with pytest.raises(ConflictError):
        api.api_request('DELETE', 'https://graph.microsoft.com/v1.0', '/x', 'fake')


def test_api_request_auth_failure_raises_typed_error(monkeypatch):
    def fake_request(method, url, **kwargs):
        raise AuthExpiredError('auth expired (401)')

    monkeypatch.setattr(api.http, 'request', fake_request)
    with pytest.raises(AuthExpiredError) as exc:
        api.api_request('GET', 'https://graph.microsoft.com/v1.0', '/me', 'fake')
    assert exc.value.exit_code == 11
