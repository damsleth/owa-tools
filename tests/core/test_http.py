"""Tests for shared HTTP mapping."""
import io
import json
import urllib.error

import pytest

from owa_core import http
from owa_core.errors import (
    AuthExpiredError,
    ConflictError,
    InternalError,
    NetworkError,
    NotFoundError,
    RateLimitedError,
    ScopeInsufficientError,
)


class FakeResp:
    def __init__(self, payload=b'', status=200, headers=None):
        self._payload = payload
        self.status = status
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self._payload


def _http_error(code, body=b'', headers=None):
    return urllib.error.HTTPError(
        'https://graph.example.test/me',
        code,
        'error',
        headers or {},
        io.BytesIO(body),
    )


def test_request_json_adds_auth_and_body_headers():
    seen = {}

    def fake_urlopen(req, timeout):
        seen['url'] = req.full_url
        seen['method'] = req.get_method()
        seen['timeout'] = timeout
        seen['auth'] = req.get_header('Authorization')
        seen['content_type'] = req.get_header('Content-type')
        seen['data'] = req.data
        payload = json.dumps({'value': [1], '@odata.nextLink': 'https://next'}).encode()
        return FakeResp(payload, headers={'request-id': 'rid-1'})

    response = http.request(
        'POST',
        'https://graph.example.test/me',
        token='fake-token',
        body={'displayName': 'Ada'},
        timeout=7,
        urlopen=fake_urlopen,
    )

    assert seen == {
        'url': 'https://graph.example.test/me',
        'method': 'POST',
        'timeout': 7,
        'auth': 'Bearer fake-token',
        'content_type': 'application/json',
        'data': b'{"displayName": "Ada"}',
    }
    assert response.json == {'value': [1], '@odata.nextLink': 'https://next'}
    assert response.next_link == 'https://next'
    assert response.request_id == 'rid-1'


def test_request_raw_returns_bytes_without_json_decode():
    response = http.request(
        'GET',
        'https://graph.example.test/content',
        token='fake-token',
        raw=True,
        urlopen=lambda req, timeout: FakeResp(b'file-bytes'),
    )
    assert response.json is None
    assert response.bytes == b'file-bytes'


def test_request_empty_body_returns_empty_object():
    response = http.request(
        'DELETE',
        'https://graph.example.test/item',
        token='fake-token',
        urlopen=lambda req, timeout: FakeResp(b'', status=204),
    )
    assert response.status == 204
    assert response.json == {}


@pytest.mark.parametrize(
    ('status', 'error_type'),
    [
        (401, AuthExpiredError),
        (403, ScopeInsufficientError),
        (404, NotFoundError),
        (409, ConflictError),
        (412, ConflictError),
        (429, RateLimitedError),
        (500, NetworkError),
        (503, NetworkError),
    ],
)
def test_http_status_maps_to_typed_errors(status, error_type):
    def fake_urlopen(req, timeout):
        raise _http_error(status, b'{"error":"boom"}')

    with pytest.raises(error_type):
        http.request('GET', 'https://graph.example.test/me', token='fake', urlopen=fake_urlopen)


def test_http_error_debug_body_is_redacted():
    access_token = '.'.join([
        'eyJhbGciOiJIUzI1NiIs',
        'eyJhdWQiOiJvd2EtdG9vbHMi',
        'c2lnbmF0dXJlZm9ydGVzdHM',
    ])

    def fake_urlopen(req, timeout):
        raise _http_error(418, f'body {access_token}'.encode())

    with pytest.raises(InternalError) as exc:
        http.request('GET', 'https://graph.example.test/me', token='fake', urlopen=fake_urlopen, debug=True)
    assert access_token not in exc.value.message
    assert '[redacted-secret]' in exc.value.message


def test_rate_limit_retry_honors_retry_after_then_succeeds():
    calls = {'n': 0}
    sleeps = []

    def fake_urlopen(req, timeout):
        calls['n'] += 1
        if calls['n'] == 1:
            raise _http_error(429, headers={'Retry-After': '3'})
        return FakeResp(json.dumps({'ok': True}).encode())

    response = http.request(
        'GET',
        'https://graph.example.test/me',
        token='fake',
        retry=1,
        sleep=sleeps.append,
        urlopen=fake_urlopen,
    )
    assert response.json == {'ok': True}
    assert sleeps == [3]
    assert calls['n'] == 2


def test_retry_after_over_cap_maps_to_rate_limited_without_sleep():
    sleeps = []

    def fake_urlopen(req, timeout):
        raise _http_error(429, headers={'Retry-After': '999'})

    with pytest.raises(RateLimitedError):
        http.request(
            'GET',
            'https://graph.example.test/me',
            token='fake',
            retry=1,
            sleep=sleeps.append,
            urlopen=fake_urlopen,
        )
    assert sleeps == []


def test_url_error_maps_to_network_error():
    def fake_urlopen(req, timeout):
        raise urllib.error.URLError('offline')

    with pytest.raises(NetworkError):
        http.request('GET', 'https://graph.example.test/me', token='fake', urlopen=fake_urlopen)


def test_invalid_json_maps_to_internal_error():
    with pytest.raises(InternalError):
        http.request(
            'GET',
            'https://graph.example.test/me',
            token='fake',
            urlopen=lambda req, timeout: FakeResp(b'not-json'),
        )


def test_paginate_yields_collection_items_and_follows_next_link():
    payloads = [
        {'value': [{'id': '1'}], '@odata.nextLink': 'https://graph.example.test/page2'},
        {'value': [{'id': '2'}]},
    ]
    seen = []

    def fake_urlopen(req, timeout):
        seen.append(req.full_url)
        return FakeResp(json.dumps(payloads.pop(0)).encode())

    items = list(http.paginate('https://graph.example.test/page1', token='fake', urlopen=fake_urlopen))
    assert items == [{'id': '1'}, {'id': '2'}]
    assert seen == ['https://graph.example.test/page1', 'https://graph.example.test/page2']


def test_paginate_honors_max_pages():
    def fake_urlopen(req, timeout):
        payload = {'value': [{'id': req.full_url}], '@odata.nextLink': 'https://next'}
        return FakeResp(json.dumps(payload).encode())

    items = list(
        http.paginate(
            'https://graph.example.test/page1',
            token='fake',
            max_pages=1,
            urlopen=fake_urlopen,
        )
    )
    assert items == [{'id': 'https://graph.example.test/page1'}]
