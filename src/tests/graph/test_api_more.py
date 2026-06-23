"""Additional owa_graph.api wrapper coverage."""
import pytest

from owa_core.errors import InternalError, NetworkError
from owa_core.http import Response
from owa_graph import api


def _response(payload=None, raw=b'{}'):
    return Response(status=200, headers={}, json={} if payload is None else payload, bytes=raw)


def test_request_forwards_method_url_body_headers_and_debug(monkeypatch):
    seen = {}

    def fake_request(method, url, **kwargs):
        seen['method'] = method
        seen['url'] = url
        seen['kwargs'] = kwargs
        return _response({'ok': True})

    monkeypatch.setattr(api.http, 'request', fake_request)
    out = api.api_request(
        'POST',
        'https://x/y',
        'a/b',
        't',
        body={'k': 'v'},
        extra_headers={'Prefer': 'foo'},
        debug=True,
    )
    assert out == {'ok': True}
    assert seen['method'] == 'POST'
    assert seen['url'] == 'https://x/y/a/b'
    assert seen['kwargs']['token'] == 't'
    assert seen['kwargs']['body'] == {'k': 'v'}
    assert seen['kwargs']['headers'] == {'Prefer': 'foo'}
    assert seen['kwargs']['debug'] is True


def test_bytes_body_forwards_unchanged(monkeypatch):
    seen = {}

    def fake_request(method, url, **kwargs):
        seen['body'] = kwargs['body']
        return _response()

    monkeypatch.setattr(api.http, 'request', fake_request)
    api.api_request('POST', 'https://x/y', 'z', 't', body=b'\x00raw\x01')
    assert seen['body'] == b'\x00raw\x01'


def test_endpoint_starting_with_http_overrides_base(monkeypatch):
    seen = {}

    def fake_request(method, url, **kwargs):
        seen['url'] = url
        return _response()

    monkeypatch.setattr(api.http, 'request', fake_request)
    api.api_request('GET', 'IGNORED', 'https://other.example/foo', 't')
    assert seen['url'] == 'https://other.example/foo'


def test_url_error_raises(monkeypatch):
    def fake_request(*args, **kwargs):
        raise NetworkError('network error: connection refused')

    monkeypatch.setattr(api.http, 'request', fake_request)
    with pytest.raises(NetworkError):
        api.api_request('GET', 'https://x/y', 'a', 't')


def test_5xx_raises(monkeypatch):
    def fake_request(*args, **kwargs):
        raise NetworkError('service unavailable (500): server boom')

    monkeypatch.setattr(api.http, 'request', fake_request)
    with pytest.raises(NetworkError):
        api.api_request('GET', 'https://x/y', 'a', 't', debug=True)


def test_internal_error_raises(monkeypatch):
    def fake_request(*args, **kwargs):
        raise InternalError('HTTP response was not valid JSON')

    monkeypatch.setattr(api.http, 'request', fake_request)
    with pytest.raises(InternalError):
        api.api_request('GET', 'https://x/y', 'a', 't')


def test_url_error_retried_once_when_retry_true(monkeypatch, capsys):
    calls = []

    def fake_request(method, url, **kwargs):
        calls.append(kwargs.get('retry'))
        if len(calls) == 1:
            raise NetworkError('network error: connection reset')
        return _response({'ok': True})

    monkeypatch.setattr(api.http, 'request', fake_request)
    out = api.api_request('GET', 'https://x/y', 'a', 't', retry=True, debug=True)
    assert out == {'ok': True}
    assert calls == [1, 0]
    assert 'retrying once' in capsys.readouterr().err


def test_url_error_not_retried_when_retry_false(monkeypatch):
    calls = []

    def fake_request(*args, **kwargs):
        calls.append(1)
        raise NetworkError('network error: reset')

    monkeypatch.setattr(api.http, 'request', fake_request)
    with pytest.raises(NetworkError):
        api.api_request('GET', 'https://x/y', 'a', 't', retry=False)
    assert len(calls) == 1


def test_url_error_persistent_with_retry_surfaces_error(monkeypatch, capsys):
    calls = []

    def fake_request(*args, **kwargs):
        calls.append(1)
        raise NetworkError('network error: still reset')

    monkeypatch.setattr(api.http, 'request', fake_request)
    with pytest.raises(NetworkError):
        api.api_request('GET', 'https://x/y', 'a', 't', retry=True, debug=True)
    assert len(calls) == 2
    assert 'still reset' in capsys.readouterr().err


def test_retry_auth_failure_raises(monkeypatch):
    from owa_core.errors import AuthExpiredError

    calls = []

    def fake_request(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise NetworkError('network error: reset')
        raise AuthExpiredError('auth expired (401)')

    monkeypatch.setattr(api.http, 'request', fake_request)
    with pytest.raises(AuthExpiredError) as exc:
        api.api_request('GET', 'https://x/y', 'a', 't', retry=True)
    assert exc.value.exit_code == 11
