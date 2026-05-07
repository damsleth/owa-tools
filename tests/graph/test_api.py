"""api_request error-path coverage. We don't want a network call here,
so urlopen is monkeypatched to a stub that raises HTTPError."""
import io
import json
import urllib.error

import pytest

from owa_graph import api


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self): return self
    def __exit__(self, *a): return False

    def read(self):
        return self._payload


def test_get_2xx_returns_parsed_json(monkeypatch):
    monkeypatch.setattr(
        api.urllib.request, 'urlopen',
        lambda req: _FakeResp(json.dumps({'displayName': 'kim'}).encode()),
    )
    out = api.api_get('https://graph.microsoft.com/v1.0', 'me', 't')
    assert out == {'displayName': 'kim'}


def test_2xx_empty_body_returns_empty_dict(monkeypatch):
    monkeypatch.setattr(
        api.urllib.request, 'urlopen', lambda req: _FakeResp(b''),
    )
    out = api.api_get('https://graph.microsoft.com/v1.0', 'me', 't')
    assert out == {}


def test_raw_returns_bytes(monkeypatch):
    monkeypatch.setattr(
        api.urllib.request, 'urlopen', lambda req: _FakeResp(b'\x00\x01\x02'),
    )
    out = api.api_get('https://graph.microsoft.com/v1.0', 'me/photo/$value', 't', raw=True)
    assert out == b'\x00\x01\x02'


def _raise_http(code):
    def _fn(req):
        raise urllib.error.HTTPError(
            req.full_url, code, 'err', {}, io.BytesIO(b'{"error":{"code":"x"}}'),
        )
    return _fn


def test_401_exits(monkeypatch):
    monkeypatch.setattr(api.urllib.request, 'urlopen', _raise_http(401))
    with pytest.raises(SystemExit) as exc:
        api.api_get('https://graph.microsoft.com/v1.0', 'me', 't')
    assert exc.value.code == 1


def test_403_exits(monkeypatch):
    monkeypatch.setattr(api.urllib.request, 'urlopen', _raise_http(403))
    with pytest.raises(SystemExit) as exc:
        api.api_get('https://graph.microsoft.com/v1.0', 'me', 't')
    assert exc.value.code == 1


def test_404_returns_none(monkeypatch):
    monkeypatch.setattr(api.urllib.request, 'urlopen', _raise_http(404))
    assert api.api_get('https://graph.microsoft.com/v1.0', 'missing', 't') is None


def test_429_returns_none(monkeypatch):
    monkeypatch.setattr(api.urllib.request, 'urlopen', _raise_http(429))
    assert api.api_get('https://graph.microsoft.com/v1.0', 'me', 't') is None


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
    out = api.build_query({'$filter': "startswith(name,'A')"})
    assert out == "$filter=startswith%28name%2C%27A%27%29"
