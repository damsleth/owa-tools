"""Tests for owa_teams.api (Graph + chatsvc HTTP helpers). No network."""
import datetime as dt

import pytest

from owa_core import errors
from owa_core.http import Response
from owa_teams import api as api_mod


def _utc(*parts):
    return dt.datetime(*parts, tzinfo=dt.timezone.utc)


def _resp(json_obj):
    return Response(status=200, headers={}, json=json_obj, bytes=b'')


# --- graph_get ----------------------------------------------------------------

def test_graph_get_joins_base_and_endpoint(monkeypatch):
    seen = {}

    def fake_request(method, url, **k):
        seen['url'] = url
        return _resp({'value': []})

    monkeypatch.setattr(api_mod.http, 'request', fake_request)
    api_mod.graph_get('https://g/v1.0', 'me/joinedTeams', 'tok')
    assert seen['url'] == 'https://g/v1.0/me/joinedTeams'


def test_graph_get_recoverable_returns_none(monkeypatch, capsys):
    monkeypatch.setattr(api_mod.http, 'request',
                        lambda *a, **k: (_ for _ in ()).throw(errors.NotFoundError('nope (404)')))
    assert api_mod.graph_get('https://g', 'x', 'tok') is None
    assert 'nope' in capsys.readouterr().err


def test_graph_get_auth_reraises(monkeypatch):
    monkeypatch.setattr(api_mod.http, 'request',
                        lambda *a, **k: (_ for _ in ()).throw(errors.AuthExpiredError('401')))
    with pytest.raises(errors.AuthExpiredError):
        api_mod.graph_get('https://g', 'x', 'tok')


def test_graph_get_generic_owaerror_returns_none(monkeypatch):
    monkeypatch.setattr(api_mod.http, 'request',
                        lambda *a, **k: (_ for _ in ()).throw(errors.OwaError('weird')))
    assert api_mod.graph_get('https://g', 'x', 'tok') is None


# --- graph_paginate -----------------------------------------------------------

def test_graph_paginate_collects(monkeypatch):
    monkeypatch.setattr(api_mod.http, 'paginate', lambda url, **k: iter([{'a': 1}, {'a': 2}]))
    assert api_mod.graph_paginate('https://g', 'me/chats', 'tok') == [{'a': 1}, {'a': 2}]


def test_graph_paginate_auth_reraises(monkeypatch):
    def boom(url, **k):
        raise errors.ScopeInsufficientError('403')
    monkeypatch.setattr(api_mod.http, 'paginate', boom)
    with pytest.raises(errors.ScopeInsufficientError):
        api_mod.graph_paginate('https://g', 'me/chats', 'tok')


def test_graph_paginate_recoverable_returns_none(monkeypatch, capsys):
    def boom(url, **k):
        raise errors.NetworkError('503')
    monkeypatch.setattr(api_mod.http, 'paginate', boom)
    assert api_mod.graph_paginate('https://g', 'me/chats', 'tok') is None
    assert '503' in capsys.readouterr().err


# --- chatsvc_messages ---------------------------------------------------------

def test_chatsvc_messages_follows_backward_link(monkeypatch):
    calls = []

    def fake_request(method, url, **k):
        calls.append(url)
        if len(calls) == 1:
            return _resp({'messages': [{'id': '2'}], '_metadata': {'backwardLink': 'https://t/older'}})
        return _resp({'messages': [{'id': '1'}], '_metadata': {}})

    monkeypatch.setattr(api_mod.http, 'request', fake_request)
    out = api_mod.chatsvc_messages('https://t/api/chatsvc/emea/v1', '19:c@thread.tacv2', 'tok')
    assert [m['id'] for m in out] == ['2', '1']
    assert calls[1] == 'https://t/older'


def test_chatsvc_messages_respects_max_pages(monkeypatch):
    calls = []

    def fake_request(method, url, **k):
        calls.append(url)
        return _resp({'messages': [{'id': str(len(calls))}], '_metadata': {'backwardLink': 'https://t/loop'}})

    monkeypatch.setattr(api_mod.http, 'request', fake_request)
    out = api_mod.chatsvc_messages('https://t/v1', 'c', 'tok', max_pages=3)
    assert len(calls) == 3
    assert len(out) == 3


def test_chatsvc_messages_since_stops_paging_and_filters(monkeypatch):
    pages = [
        {'messages': [{'id': '3', 'originalarrivaltime': '2026-06-10T00:00:00Z'}],
         '_metadata': {'backwardLink': 'https://t/p2'}},
        {'messages': [{'id': '2', 'originalarrivaltime': '2026-06-05T00:00:00Z'},
                      {'id': '1', 'originalarrivaltime': '2026-05-01T00:00:00Z'}],
         '_metadata': {'backwardLink': 'https://t/p3'}},
    ]
    calls = []

    def fake_request(method, url, **k):
        resp = _resp(pages[len(calls)])
        calls.append(url)
        return resp

    monkeypatch.setattr(api_mod.http, 'request', fake_request)
    out = api_mod.chatsvc_messages('https://t/v1', 'c', 'tok', since_dt=_utc(2026, 6, 1))
    # Page 2 dips below the cutoff -> stop after it; the May message is filtered.
    assert len(calls) == 2
    assert [m['id'] for m in out] == ['3', '2']


def test_chatsvc_messages_since_keeps_unparseable_timestamps(monkeypatch):
    monkeypatch.setattr(api_mod.http, 'request', lambda *a, **k: _resp(
        {'messages': [{'id': 'x'}], '_metadata': {}}))
    out = api_mod.chatsvc_messages('https://t/v1', 'c', 'tok', since_dt=_utc(2026, 6, 1))
    assert [m['id'] for m in out] == ['x']


def test_chatsvc_messages_stops_on_non_list_payload(monkeypatch):
    monkeypatch.setattr(api_mod.http, 'request', lambda *a, **k: _resp({'error': 'x'}))
    assert api_mod.chatsvc_messages('https://t/v1', 'c', 'tok') == []


def test_chatsvc_messages_auth_reraises(monkeypatch):
    def boom(*a, **k):
        raise errors.AuthExpiredError('401')
    monkeypatch.setattr(api_mod.http, 'request', boom)
    with pytest.raises(errors.AuthExpiredError):
        api_mod.chatsvc_messages('https://t/v1', 'c', 'tok')


def test_chatsvc_messages_recoverable_returns_none(monkeypatch, capsys):
    def boom(*a, **k):
        raise errors.RateLimitedError('429')
    monkeypatch.setattr(api_mod.http, 'request', boom)
    assert api_mod.chatsvc_messages('https://t/v1', 'c', 'tok') is None
    assert '429' in capsys.readouterr().err


# --- Retry-After budget (429 ride-through) ------------------------------------

def test_graph_get_passes_default_retry_budget(monkeypatch):
    seen = {}

    def fake_request(method, url, **k):
        seen['retry'] = k.get('retry')
        return _resp({'value': []})

    monkeypatch.setattr(api_mod.http, 'request', fake_request)
    api_mod.graph_get('https://g', 'me/joinedTeams', 'tok')
    assert seen['retry'] == api_mod.DEFAULT_RETRY
    assert api_mod.DEFAULT_RETRY > 0


def test_graph_paginate_passes_retry_budget(monkeypatch):
    seen = {}

    def fake_paginate(url, **k):
        seen['retry'] = k.get('retry')
        return iter([])

    monkeypatch.setattr(api_mod.http, 'paginate', fake_paginate)
    api_mod.graph_paginate('https://g', 'teams/t/channels', 'tok')
    assert seen['retry'] == api_mod.DEFAULT_RETRY


def test_chatsvc_messages_passes_retry_budget(monkeypatch):
    seen = {}

    def fake_request(method, url, **k):
        seen['retry'] = k.get('retry')
        return _resp({'messages': [], '_metadata': {}})

    monkeypatch.setattr(api_mod.http, 'request', fake_request)
    api_mod.chatsvc_messages('https://t/v1', 'c', 'tok')
    assert seen['retry'] == api_mod.DEFAULT_RETRY
