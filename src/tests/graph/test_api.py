"""owa-graph API wrapper coverage."""
import pytest

from owa_core.errors import (
    AuthExpiredError,
    NotFoundError,
    RateLimitedError,
    ScopeInsufficientError,
)
from owa_core.http import Response
from owa_graph import api


def _response(payload=None, raw=b'{}'):
    return Response(status=200, headers={}, json={} if payload is None else payload, bytes=raw)


def test_get_2xx_returns_parsed_json(monkeypatch):
    monkeypatch.setattr(api.http, 'request', lambda *a, **k: _response({'displayName': 'kim'}))
    assert api.api_get('https://graph.microsoft.com/v1.0', 'me', 't') == {'displayName': 'kim'}


def test_empty_body_returns_empty_dict(monkeypatch):
    monkeypatch.setattr(api.http, 'request', lambda *a, **k: _response({}))
    assert api.api_get('https://graph.microsoft.com/v1.0', 'me', 't') == {}


def test_raw_returns_bytes(monkeypatch):
    monkeypatch.setattr(api.http, 'request', lambda *a, **k: _response(raw=b'\x00\x01\x02'))
    out = api.api_get('https://graph.microsoft.com/v1.0', 'me/photo/$value', 't', raw=True)
    assert out == b'\x00\x01\x02'


def test_401_raises_auth_error(monkeypatch):
    def fake_request(*args, **kwargs):
        raise AuthExpiredError('auth expired (401)')

    monkeypatch.setattr(api.http, 'request', fake_request)
    with pytest.raises(AuthExpiredError) as exc:
        api.api_get('https://graph.microsoft.com/v1.0', 'me', 't')
    assert exc.value.exit_code == 11


def test_403_raises_scope_error(monkeypatch):
    def fake_request(*args, **kwargs):
        raise ScopeInsufficientError('access denied (403)')

    monkeypatch.setattr(api.http, 'request', fake_request)
    with pytest.raises(ScopeInsufficientError) as exc:
        api.api_get('https://graph.microsoft.com/v1.0', 'me', 't')
    assert exc.value.exit_code == 12


def test_404_raises(monkeypatch):
    def fake_request(*args, **kwargs):
        raise NotFoundError('not found (404)')

    monkeypatch.setattr(api.http, 'request', fake_request)
    with pytest.raises(NotFoundError):
        api.api_get('https://graph.microsoft.com/v1.0', 'missing', 't')


def test_429_raises(monkeypatch):
    def fake_request(*args, **kwargs):
        raise RateLimitedError('rate limited (429)')

    monkeypatch.setattr(api.http, 'request', fake_request)
    with pytest.raises(RateLimitedError):
        api.api_get('https://graph.microsoft.com/v1.0', 'me', 't')


def test_build_url_basic():
    assert api.build_url('https://x/y', 'a/b') == 'https://x/y/a/b'
    assert api.build_url('https://x/y/', '/a/b') == 'https://x/y/a/b'


def test_build_url_with_query():
    assert api.build_url(
        'https://x/y', '/a', [('$top', '5'), ('$select', 'id,name')],
    ) == 'https://x/y/a?$top=5&$select=id%2Cname'


def test_build_url_preserves_existing_query():
    assert api.build_url(
        'https://x/y', '/a?$top=5', [('$select', 'id')],
    ) == 'https://x/y/a?$top=5&$select=id'


def test_build_query_url_encodes_values():
    from owa_core.query import build_query
    out = build_query({'$filter': "startswith(name,'A')"})
    assert out == "$filter=startswith%28name%2C%27A%27%29"
