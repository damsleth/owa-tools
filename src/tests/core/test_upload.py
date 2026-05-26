"""Tests for the generic Graph upload-session driver."""
import io
import urllib.error

import pytest

from owa_core import upload
from owa_core.errors import InternalError, NetworkError, RateLimitedError


class FakeResp:
    def __init__(self, payload=b'', status=200):
        self._payload = payload
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self._payload


def _http_error(code, body=b'', headers=None):
    return urllib.error.HTTPError(
        'https://up.example.test/session',
        code,
        'error',
        headers or {},
        io.BytesIO(body),
    )


def test_normalize_chunk_size_rounds_to_320kib_multiple():
    assert upload._normalize_chunk_size(upload.CHUNK_MULTIPLE) == upload.CHUNK_MULTIPLE
    # Below the multiple snaps up to one multiple.
    assert upload._normalize_chunk_size(100) == upload.CHUNK_MULTIPLE
    # Non-multiple rounds down to the nearest multiple.
    assert upload._normalize_chunk_size(upload.CHUNK_MULTIPLE * 3 + 7) == upload.CHUNK_MULTIPLE * 3
    assert upload.DEFAULT_CHUNK_SIZE == 10 * 1024 * 1024


def test_invalid_chunk_size_raises():
    with pytest.raises(InternalError):
        upload._normalize_chunk_size(0)


def test_single_chunk_upload_returns_final_item_and_omits_auth():
    seen = []

    def fake_urlopen(req, timeout):
        seen.append({
            'method': req.get_method(),
            'auth': req.get_header('Authorization'),
            'range': req.get_header('Content-range'),
            'length': req.get_header('Content-length'),
            'data': req.data,
        })
        return FakeResp(b'{"id":"item-1","name":"x"}', status=201)

    out = upload.upload_session(
        'https://up.example.test/session',
        b'hello',
        urlopen=fake_urlopen,
    )
    assert out == {'id': 'item-1', 'name': 'x'}
    assert len(seen) == 1
    assert seen[0]['method'] == 'PUT'
    # No bearer token on the pre-signed uploadUrl.
    assert seen[0]['auth'] is None
    assert seen[0]['range'] == 'bytes 0-4/5'
    assert seen[0]['length'] == '5'
    assert seen[0]['data'] == b'hello'


def test_multi_chunk_upload_sends_correct_ranges():
    # chunk_size = one 320KiB multiple; content spans 2.5 chunks.
    chunk = upload.CHUNK_MULTIPLE
    total = chunk * 2 + 10
    content = b'a' * total
    ranges = []
    statuses = []

    def fake_urlopen(req, timeout):
        ranges.append(req.get_header('Content-range'))
        # 202 for intermediate, 200 with body for final.
        start_end = req.get_header('Content-range')
        end = int(start_end.split('/')[0].split('-')[1])
        if end + 1 >= total:
            statuses.append('final')
            return FakeResp(b'{"id":"done"}', status=200)
        statuses.append('intermediate')
        return FakeResp(b'{}', status=202)

    out = upload.upload_session(
        'https://up.example.test/session',
        content,
        chunk_size=chunk,
        urlopen=fake_urlopen,
    )
    assert out == {'id': 'done'}
    assert ranges == [
        f'bytes 0-{chunk - 1}/{total}',
        f'bytes {chunk}-{2 * chunk - 1}/{total}',
        f'bytes {2 * chunk}-{total - 1}/{total}',
    ]
    assert statuses == ['intermediate', 'intermediate', 'final']


def test_intermediate_chunk_with_unexpected_status_raises():
    def fake_urlopen(req, timeout):
        # Return 200 (final-looking) on an intermediate chunk.
        return FakeResp(b'{}', status=200)

    with pytest.raises(InternalError, match='non-final upload chunk'):
        upload.upload_session(
            'https://up.example.test/session',
            b'a' * (upload.CHUNK_MULTIPLE + 5),
            chunk_size=upload.CHUNK_MULTIPLE,
            urlopen=fake_urlopen,
        )


def test_final_chunk_non_2xx_status_raises():
    def fake_urlopen(req, timeout):
        return FakeResp(b'{}', status=202)

    with pytest.raises(InternalError, match='did not complete'):
        upload.upload_session(
            'https://up.example.test/session',
            b'small',
            urlopen=fake_urlopen,
        )


def test_final_payload_without_dict_raises():
    def fake_urlopen(req, timeout):
        return FakeResp(b'[]', status=200)

    with pytest.raises(InternalError, match='without an item payload'):
        upload.upload_session(
            'https://up.example.test/session',
            b'small',
            urlopen=fake_urlopen,
        )


def test_empty_final_body_returns_empty_dict():
    def fake_urlopen(req, timeout):
        return FakeResp(b'', status=200)

    out = upload.upload_session(
        'https://up.example.test/session',
        b'small',
        urlopen=fake_urlopen,
    )
    assert out == {}


def test_invalid_json_response_raises():
    def fake_urlopen(req, timeout):
        return FakeResp(b'not-json', status=200)

    with pytest.raises(InternalError, match='not valid JSON'):
        upload.upload_session(
            'https://up.example.test/session',
            b'small',
            urlopen=fake_urlopen,
        )


def test_chunk_http_error_propagates_redacted():
    token = '.'.join([
        'eyJhbGciOiJIUzI1NiIs',
        'eyJhdWQiOiJvd2EtdG9vbHMi',
        'c2lnbmF0dXJlZm9ydGVzdHM',
    ])

    def fake_urlopen(req, timeout):
        raise _http_error(400, f'bad {token}'.encode())

    with pytest.raises(InternalError) as exc:
        upload.upload_session(
            'https://up.example.test/session',
            b'small',
            debug=True,
            urlopen=fake_urlopen,
        )
    assert token not in exc.value.message
    assert '[redacted-secret]' in exc.value.message


def test_chunk_network_error_maps_to_network_error():
    def fake_urlopen(req, timeout):
        raise urllib.error.URLError('offline')

    with pytest.raises(NetworkError):
        upload.upload_session(
            'https://up.example.test/session',
            b'small',
            urlopen=fake_urlopen,
        )


def test_chunk_retry_honors_retry_after_then_succeeds():
    calls = {'n': 0}
    sleeps = []

    def fake_urlopen(req, timeout):
        calls['n'] += 1
        if calls['n'] == 1:
            raise _http_error(503, headers={'Retry-After': '2'})
        return FakeResp(b'{"id":"ok"}', status=200)

    out = upload.upload_session(
        'https://up.example.test/session',
        b'small',
        retry=1,
        sleep=sleeps.append,
        urlopen=fake_urlopen,
        debug=True,
    )
    assert out == {'id': 'ok'}
    assert sleeps == [2]
    assert calls['n'] == 2


def test_chunk_retry_after_over_cap_raises_rate_limited():
    def fake_urlopen(req, timeout):
        raise _http_error(429, headers={'Retry-After': '999'})

    with pytest.raises(RateLimitedError):
        upload.upload_session(
            'https://up.example.test/session',
            b'small',
            retry=1,
            sleep=lambda _s: None,
            urlopen=fake_urlopen,
        )
