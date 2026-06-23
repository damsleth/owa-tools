"""owa-mail API wrapper tests."""
import pytest

from owa_core.errors import AuthExpiredError, NotFoundError
from owa_core.http import Response
from owa_mail import api


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
        'me/messages',
        'fake-token',
    )
    assert out == {'ok': True}
    assert seen['method'] == 'GET'
    assert seen['url'] == 'https://outlook.office.com/api/v2.0/me/messages'
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


def test_api_get_binary_returns_bytes(monkeypatch):
    def fake_request(method, url, **kwargs):
        assert kwargs['raw'] is True
        assert url.endswith('/$value')
        return Response(status=200, headers={}, json=None, bytes=b'rawbytes')

    monkeypatch.setattr(api.http, 'request', fake_request)
    out = api.api_get_binary(
        'https://outlook.office.com/api/v2.0',
        'me/messages/m1/attachments/a1/$value',
        'tok',
    )
    assert out == b'rawbytes'


def test_api_get_binary_recoverable_error_raises(monkeypatch):
    def fake_request(method, url, **kwargs):
        raise NotFoundError('not found (404)')

    monkeypatch.setattr(api.http, 'request', fake_request)
    with pytest.raises(NotFoundError):
        api.api_get_binary('https://b', 'e', 'tok')


def test_api_get_binary_auth_error_raises(monkeypatch):
    def fake_request(method, url, **kwargs):
        raise AuthExpiredError('auth expired (401)')

    monkeypatch.setattr(api.http, 'request', fake_request)
    with pytest.raises(AuthExpiredError):
        api.api_get_binary('https://b', 'e', 'tok')


def test_api_upload_attachment_session_drives_helper(monkeypatch):
    seen = {}

    def fake_request(method, url, **kwargs):
        seen['create_url'] = url
        seen['body'] = kwargs.get('body')
        return Response(
            status=201, headers={}, json={'uploadUrl': 'https://up.test/x'}, bytes=b'{}',
        )

    def fake_upload(upload_url, content, **kwargs):
        seen['upload_url'] = upload_url
        seen['content'] = content
        return {'id': 'att-final'}

    monkeypatch.setattr(api.http, 'request', fake_request)
    monkeypatch.setattr(api.upload_mod, 'upload_session', fake_upload)

    out = api.api_upload_attachment_session(
        'https://outlook.office.com/api/v2.0',
        'me/messages/d1/attachments/createUploadSession',
        'tok',
        {'AttachmentItem': {'attachmentType': 'file', 'name': 'big', 'size': 9}},
        b'x' * 9,
    )
    assert out == {'id': 'att-final'}
    assert seen['create_url'].endswith('/createUploadSession')
    assert seen['upload_url'] == 'https://up.test/x'
    assert seen['content'] == b'x' * 9


def test_api_upload_attachment_session_no_upload_url(monkeypatch, capsys):
    def fake_request(method, url, **kwargs):
        return Response(status=201, headers={}, json={'noUrl': True}, bytes=b'{}')

    monkeypatch.setattr(api.http, 'request', fake_request)
    assert api.api_upload_attachment_session(
        'https://b', 'e', 'tok', {}, b'x',
    ) is None
    assert 'no uploadUrl' in capsys.readouterr().err


def test_api_upload_attachment_session_create_failure_raises(monkeypatch):
    def fake_request(method, url, **kwargs):
        raise NotFoundError('not found (404)')

    monkeypatch.setattr(api.http, 'request', fake_request)
    with pytest.raises(NotFoundError):
        api.api_upload_attachment_session('https://b', 'e', 'tok', {}, b'x')


def test_api_upload_attachment_session_non_dict_body(monkeypatch, capsys):
    def fake_request(method, url, **kwargs):
        return Response(status=201, headers={}, json=[], bytes=b'[]')

    monkeypatch.setattr(api.http, 'request', fake_request)
    assert api.api_upload_attachment_session('https://b', 'e', 'tok', {}, b'x') is None
    assert 'returned no body' in capsys.readouterr().err


def test_api_upload_attachment_session_upload_error_raises(monkeypatch):
    from owa_core.errors import NetworkError

    def fake_request(method, url, **kwargs):
        return Response(status=201, headers={}, json={'uploadUrl': 'https://up.test/x'}, bytes=b'{}')

    def fake_upload(upload_url, content, **kwargs):
        raise NetworkError('network error: down')

    monkeypatch.setattr(api.http, 'request', fake_request)
    monkeypatch.setattr(api.upload_mod, 'upload_session', fake_upload)
    with pytest.raises(NetworkError):
        api.api_upload_attachment_session('https://b', 'e', 'tok', {}, b'x')


def test_api_upload_attachment_session_auth_error_during_create(monkeypatch):
    def fake_request(method, url, **kwargs):
        raise AuthExpiredError('auth expired (401)')

    monkeypatch.setattr(api.http, 'request', fake_request)
    with pytest.raises(AuthExpiredError):
        api.api_upload_attachment_session('https://b', 'e', 'tok', {}, b'x')
