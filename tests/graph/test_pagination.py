"""Pagination + retry coverage for the graph wrapper."""
from owa_core.errors import RateLimitedError
from owa_graph import api


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


def test_paginate_walks_nextlinks(monkeypatch):
    pages = [
        {'value': [{'id': 1}, {'id': 2}], '@odata.nextLink': 'https://x/p2'},
        {'value': [{'id': 3}], '@odata.nextLink': 'https://x/p3'},
        {'value': [{'id': 4}, {'id': 5}]},
    ]
    seen_urls = []

    def _fake(method, base, endpoint, token, **kwargs):
        seen_urls.append(endpoint)
        return pages.pop(0)

    monkeypatch.setattr(api, 'api_request', _fake)
    out = list(api.paginate('GET', 'https://x/p1', 'tok'))
    assert [item['id'] for item in out] == [1, 2, 3, 4, 5]
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
        {'value': [{'i': i}], '@odata.nextLink': f'https://x/p{i + 1}'}
        for i in range(10)
    ]
    monkeypatch.setattr(api, 'api_request', lambda *a, **k: pages.pop(0))
    out = list(api.paginate('GET', 'https://x/p0', 'tok', max_pages=3))
    assert len(out) == 3


def test_paginate_yields_when_value_empty(monkeypatch):
    monkeypatch.setattr(api, 'api_request', lambda *a, **k: {'value': []})
    assert list(api.paginate('GET', 'https://x/y', 'tok')) == []


def test_retry_flag_forwards_to_core_http(monkeypatch):
    seen = {}

    def fake_request(method, url, **kwargs):
        seen['retry'] = kwargs['retry']
        from owa_core.http import Response
        return Response(status=200, headers={}, json={'ok': True}, bytes=b'{}')

    monkeypatch.setattr(api.http, 'request', fake_request)
    assert api.api_request('GET', 'https://x', 'y', 'tok', retry=True) == {'ok': True}
    assert seen['retry'] == 1


def test_retry_caps_at_60s_and_returns_none(monkeypatch, capsys):
    def fake_request(*args, **kwargs):
        raise RateLimitedError('rate limited (429); server asked for 3600s (>cap 60s). Try again later.')

    monkeypatch.setattr(api.http, 'request', fake_request)
    assert api.api_request('GET', 'https://x', 'y', 'tok', retry=True) is None
    err = capsys.readouterr().err
    assert '3600s' in err
    assert '>cap' in err


def test_503_without_retry_returns_none(monkeypatch, capsys):
    from owa_core.errors import NetworkError

    def fake_request(*args, **kwargs):
        raise NetworkError('service unavailable (503)')

    monkeypatch.setattr(api.http, 'request', fake_request)
    assert api.api_request('GET', 'https://x', 'y', 'tok') is None
    assert 'service unavailable' in capsys.readouterr().err
