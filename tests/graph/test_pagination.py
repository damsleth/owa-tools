"""Pagination + retry coverage."""
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
    def read(self): return self._payload


# ---------------------------------------------------------------------------
# _parse_retry_after
# ---------------------------------------------------------------------------

def test_parse_retry_after_seconds():
    assert api._parse_retry_after('30') == 30


def test_parse_retry_after_zero():
    assert api._parse_retry_after('0') == 0


def test_parse_retry_after_negative_clamped():
    assert api._parse_retry_after('-5') == 0


def test_parse_retry_after_none_returns_default():
    assert api._parse_retry_after(None, default=2) == 2
    assert api._parse_retry_after('', default=7) == 7


def test_parse_retry_after_http_date_falls_back():
    assert api._parse_retry_after('Wed, 21 Oct 2026 07:28:00 GMT', default=4) == 4


# ---------------------------------------------------------------------------
# paginate
# ---------------------------------------------------------------------------

def test_paginate_walks_nextlinks(monkeypatch):
    pages = [
        {'value': [{'id': 1}, {'id': 2}], '@odata.nextLink': 'https://x/p2'},
        {'value': [{'id': 3}], '@odata.nextLink': 'https://x/p3'},
        {'value': [{'id': 4}, {'id': 5}]},
    ]
    seen_urls = []
    def _fake(method, base, endpoint, token, **k):
        seen_urls.append(endpoint)
        return pages.pop(0)
    monkeypatch.setattr(api, 'api_request', _fake)
    out = list(api.paginate('GET', 'https://x/p1', 'tok'))
    assert [i['id'] for i in out] == [1, 2, 3, 4, 5]
    assert seen_urls == ['https://x/p1', 'https://x/p2', 'https://x/p3']


def test_paginate_handles_single_entity_response(monkeypatch):
    monkeypatch.setattr(
        api, 'api_request',
        lambda *a, **k: {'displayName': 'kim', 'id': 'x'},
    )
    out = list(api.paginate('GET', 'https://x/me', 'tok'))
    assert out == [{'displayName': 'kim', 'id': 'x'}]


def test_paginate_stops_on_none(monkeypatch):
    monkeypatch.setattr(api, 'api_request', lambda *a, **k: None)
    assert list(api.paginate('GET', 'https://x/y', 'tok')) == []


def test_paginate_respects_max_pages(monkeypatch):
    pages = [
        {'value': [{'i': i}], '@odata.nextLink': f'https://x/p{i+1}'}
        for i in range(10)
    ]
    monkeypatch.setattr(api, 'api_request', lambda *a, **k: pages.pop(0))
    out = list(api.paginate('GET', 'https://x/p0', 'tok', max_pages=3))
    assert len(out) == 3


def test_paginate_yields_when_value_empty(monkeypatch):
    monkeypatch.setattr(api, 'api_request', lambda *a, **k: {'value': []})
    assert list(api.paginate('GET', 'https://x/y', 'tok')) == []


# ---------------------------------------------------------------------------
# api_request retry behavior
# ---------------------------------------------------------------------------

def _http_error(code, retry_after=None):
    headers = {}
    if retry_after is not None:
        headers['Retry-After'] = retry_after
    def _fn(req):
        raise urllib.error.HTTPError(
            req.full_url, code, 'err', headers, io.BytesIO(b'{}'),
        )
    return _fn


def test_429_with_retry_sleeps_and_retries(monkeypatch):
    calls = {'n': 0}
    def _urlopen(req):
        calls['n'] += 1
        if calls['n'] == 1:
            raise urllib.error.HTTPError(
                req.full_url, 429, 'rl', {'Retry-After': '1'},
                io.BytesIO(b'{}'),
            )
        return _FakeResp(b'{"ok":true}')
    slept = []
    monkeypatch.setattr(api.urllib.request, 'urlopen', _urlopen)
    monkeypatch.setattr(api.time, 'sleep', lambda s: slept.append(s))
    out = api.api_request('GET', 'https://x', 'y', 'tok', retry=True)
    assert out == {'ok': True}
    assert slept == [1]
    assert calls['n'] == 2


def test_503_with_retry_uses_default_when_no_header(monkeypatch):
    calls = {'n': 0}
    def _urlopen(req):
        calls['n'] += 1
        if calls['n'] == 1:
            raise urllib.error.HTTPError(
                req.full_url, 503, 'down', {}, io.BytesIO(b'{}'),
            )
        return _FakeResp(b'{}')
    slept = []
    monkeypatch.setattr(api.urllib.request, 'urlopen', _urlopen)
    monkeypatch.setattr(api.time, 'sleep', lambda s: slept.append(s))
    api.api_request('GET', 'https://x', 'y', 'tok', retry=True)
    # Default retry-after is 2s.
    assert slept == [2]


def test_retry_caps_at_60s_and_returns_none(monkeypatch, capsys):
    monkeypatch.setattr(
        api.urllib.request, 'urlopen',
        _http_error(429, retry_after='3600'),
    )
    out = api.api_request('GET', 'https://x', 'y', 'tok', retry=True)
    assert out is None
    err = capsys.readouterr().err
    assert '3600s' in err
    assert '>cap' in err


def test_retry_only_once_no_loop(monkeypatch):
    calls = {'n': 0}
    def _urlopen(req):
        calls['n'] += 1
        raise urllib.error.HTTPError(
            req.full_url, 429, 'rl', {'Retry-After': '0'},
            io.BytesIO(b'{}'),
        )
    monkeypatch.setattr(api.urllib.request, 'urlopen', _urlopen)
    monkeypatch.setattr(api.time, 'sleep', lambda s: None)
    out = api.api_request('GET', 'https://x', 'y', 'tok', retry=True)
    assert out is None
    # First attempt + one retry = 2 calls, never more.
    assert calls['n'] == 2


def test_429_without_retry_returns_none_no_sleep(monkeypatch):
    monkeypatch.setattr(api.urllib.request, 'urlopen', _http_error(429))
    slept = []
    monkeypatch.setattr(api.time, 'sleep', lambda s: slept.append(s))
    out = api.api_request('GET', 'https://x', 'y', 'tok', retry=False)
    assert out is None
    assert slept == []


def test_503_without_retry_returns_none(monkeypatch, capsys):
    monkeypatch.setattr(api.urllib.request, 'urlopen', _http_error(503))
    out = api.api_request('GET', 'https://x', 'y', 'tok')
    assert out is None
    assert 'service unavailable' in capsys.readouterr().err


def test_retry_debug_logs_wait(monkeypatch, capsys):
    calls = {'n': 0}
    def _urlopen(req):
        calls['n'] += 1
        if calls['n'] == 1:
            raise urllib.error.HTTPError(
                req.full_url, 429, 'rl', {'Retry-After': '3'},
                io.BytesIO(b'{}'),
            )
        return _FakeResp(b'{}')
    monkeypatch.setattr(api.urllib.request, 'urlopen', _urlopen)
    monkeypatch.setattr(api.time, 'sleep', lambda s: None)
    api.api_request('GET', 'https://x', 'y', 'tok', retry=True, debug=True)
    err = capsys.readouterr().err
    assert 'retrying in 3s' in err
