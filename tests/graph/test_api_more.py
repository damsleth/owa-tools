"""Additional api.py coverage: debug logging, base+endpoint joining,
URLError, bytes body, extra_headers."""
import io
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


def test_debug_logs_method_url_and_body(monkeypatch, capsys):
    captured = {}
    def _urlopen(req):
        captured['url'] = req.full_url
        captured['headers'] = dict(req.header_items())
        return _FakeResp(b'{}')
    monkeypatch.setattr(api.urllib.request, 'urlopen', _urlopen)
    api.api_request(
        'POST', 'https://x/y', 'a/b', 't',
        body={'k': 'v'}, debug=True,
    )
    err = capsys.readouterr().err
    assert 'POST https://x/y/a/b' in err
    assert '"k": "v"' in err
    assert captured['headers'].get('Content-type') == 'application/json'


def test_bytes_body_passes_through_unencoded(monkeypatch):
    seen = {}
    def _urlopen(req):
        seen['data'] = req.data
        return _FakeResp(b'{}')
    monkeypatch.setattr(api.urllib.request, 'urlopen', _urlopen)
    api.api_request('POST', 'https://x/y', 'z', 't', body=b'\x00raw\x01')
    assert seen['data'] == b'\x00raw\x01'


def test_extra_headers_merged(monkeypatch):
    seen = {}
    def _urlopen(req):
        seen['headers'] = dict(req.header_items())
        return _FakeResp(b'{}')
    monkeypatch.setattr(api.urllib.request, 'urlopen', _urlopen)
    api.api_request(
        'GET', 'https://x/y', 'a', 't',
        extra_headers={'Prefer': 'foo'},
    )
    # urllib title-cases header keys ('Prefer' -> 'Prefer').
    assert 'Prefer' in seen['headers']
    assert seen['headers']['Prefer'] == 'foo'


def test_url_error_returns_none(monkeypatch, capsys):
    def _raise(req):
        raise urllib.error.URLError('connection refused')
    monkeypatch.setattr(api.urllib.request, 'urlopen', _raise)
    out = api.api_request('GET', 'https://x/y', 'a', 't')
    assert out is None
    assert 'connection refused' in capsys.readouterr().err


def test_5xx_returns_none_with_debug_body(monkeypatch, capsys):
    def _raise(req):
        raise urllib.error.HTTPError(
            req.full_url, 500, 'srv', {}, io.BytesIO(b'server boom'),
        )
    monkeypatch.setattr(api.urllib.request, 'urlopen', _raise)
    out = api.api_request('GET', 'https://x/y', 'a', 't', debug=True)
    assert out is None
    err = capsys.readouterr().err
    assert 'HTTP 500' in err
    assert 'server boom' in err


def test_403_logs_body_in_debug(monkeypatch, capsys):
    def _raise(req):
        raise urllib.error.HTTPError(
            req.full_url, 403, 'denied', {}, io.BytesIO(b'no scope'),
        )
    monkeypatch.setattr(api.urllib.request, 'urlopen', _raise)
    with pytest.raises(SystemExit):
        api.api_request('GET', 'https://x/y', 'a', 't', debug=True)
    err = capsys.readouterr().err
    assert 'access denied' in err
    assert 'no scope' in err


def test_endpoint_starting_with_http_overrides_base(monkeypatch):
    seen = {}
    def _urlopen(req):
        seen['url'] = req.full_url
        return _FakeResp(b'{}')
    monkeypatch.setattr(api.urllib.request, 'urlopen', _urlopen)
    api.api_request(
        'GET', 'IGNORED', 'https://other.example/foo', 't',
    )
    assert seen['url'] == 'https://other.example/foo'


def test_url_error_retried_once_when_retry_true(monkeypatch, capsys):
    """retry=True absorbs a single transport flake and retries once."""
    calls = []
    def _flake(req):
        calls.append(req.full_url)
        if len(calls) == 1:
            raise urllib.error.URLError('connection reset')
        return _FakeResp(b'{"ok":true}')
    monkeypatch.setattr(api.urllib.request, 'urlopen', _flake)
    out = api.api_request('GET', 'https://x/y', 'a', 't', retry=True)
    assert out == {'ok': True}
    assert len(calls) == 2


def test_url_error_not_retried_when_retry_false(monkeypatch, capsys):
    calls = []
    def _flake(req):
        calls.append(1)
        raise urllib.error.URLError('reset')
    monkeypatch.setattr(api.urllib.request, 'urlopen', _flake)
    out = api.api_request('GET', 'https://x/y', 'a', 't', retry=False)
    assert out is None
    assert len(calls) == 1


def test_url_error_persistent_with_retry_surfaces_error(monkeypatch, capsys):
    """If the second attempt also fails, give up and surface the error."""
    calls = []
    def _flake(req):
        calls.append(1)
        raise urllib.error.URLError('still reset')
    monkeypatch.setattr(api.urllib.request, 'urlopen', _flake)
    out = api.api_request('GET', 'https://x/y', 'a', 't', retry=True, debug=True)
    assert out is None
    assert len(calls) == 2
    err = capsys.readouterr().err
    assert 'still reset' in err
