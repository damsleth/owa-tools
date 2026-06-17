"""Gate tests for the owa-graph TUI navigation engine (Phase 1, Agent A1).

Covers classification (incl. the non-JSON → opaque branch), row building and
caps, the three `next_path` id-shapes, the three pagination continuation
shapes (OData `@odata.nextLink`, ARM bare `nextLink`, devops case-insensitive
header), the curses-safe error mapping of `_tui_get`, and the graph prefix
index / template normalization / scope hints.
"""
from __future__ import annotations

import pytest

from owa_core.errors import (
    AuthExpiredError,
    InternalError,
    NetworkError,
    NotFoundError,
    RateLimitedError,
    ScopeInsufficientError,
)
from owa_graph import tui_nav

# ---------------------------------------------------------------------------
# classify_response
# ---------------------------------------------------------------------------

def test_classify_collection(make_result, graph_collection):
    kind, payload = tui_nav.classify_response(make_result(graph_collection))
    assert kind == 'collection'
    assert payload['value'][0]['displayName'] == 'Ada'


def test_classify_object(make_result, teams_opaque):
    kind, payload = tui_nav.classify_response(make_result(teams_opaque))
    assert kind == 'object'
    assert 'value' not in payload


def test_classify_scalar(make_result, tier_d_scalar):
    kind, payload = tui_nav.classify_response(make_result(tier_d_scalar))
    assert kind == 'scalar'
    assert payload == 'OK'


def test_classify_non_json_is_opaque(make_result, non_json_body):
    # The JSON-shaped fixtures never reach this branch; only a real non-JSON
    # body does. Payload is the raw bytes, preserved for a hex preview.
    kind, payload = tui_nav.classify_response(make_result(non_json_body))
    assert kind == 'opaque'
    assert payload == non_json_body


def test_classify_top_level_list_is_collection(make_result):
    kind, payload = tui_nav.classify_response(make_result([{'id': 'x'}]))
    assert kind == 'collection'
    assert payload['value'] == [{'id': 'x'}]


# ---------------------------------------------------------------------------
# build_rows
# ---------------------------------------------------------------------------

def test_build_rows_collection_labels_and_drillable(graph_collection):
    rows = tui_nav.build_rows('collection', graph_collection)
    assert [r.label for r in rows] == ['Ada', 'Babbage']
    assert all(r.drillable for r in rows)
    assert rows[0].target == '11111111-1111-1111-1111-111111111111'


def test_build_rows_empty_collection():
    rows = tui_nav.build_rows('collection', {'value': []})
    assert len(rows) == 1
    assert rows[0].label == '(no items)'
    assert not rows[0].drillable


def test_build_rows_caps_with_sentinel():
    payload = {'value': [{'id': str(i)} for i in range(tui_nav.MAX_ROWS + 5)]}
    rows = tui_nav.build_rows('collection', payload)
    assert len(rows) == tui_nav.MAX_ROWS + 1
    assert rows[-1].dim and not rows[-1].drillable
    assert '5 more' in rows[-1].label


def test_build_rows_opaque_non_drillable(make_result, non_json_body):
    kind, payload = tui_nav.classify_response(make_result(non_json_body))
    rows = tui_nav.build_rows(kind, payload)
    assert len(rows) == 1
    assert not rows[0].drillable


def test_build_rows_object_keys_and_navlink(teams_opaque):
    rows = tui_nav.build_rows('object', teams_opaque)
    labels = [r.label for r in rows]
    # etag is on the deny-list; properties shows as a non-drillable key row.
    assert any(label.startswith('properties:') for label in labels)
    assert not any(label.startswith('etag') for label in labels)


def test_build_rows_object_same_host_navlink_drillable():
    payload = {
        'manager@odata.navigationLink': 'https://graph.microsoft.com/v1.0/users/x/manager',
        'photo@odata.navigationLink': 'https://cdn.example.com/p.jpg',
    }
    rows = tui_nav.build_rows('object', payload, host='graph.microsoft.com')
    by_drillable = {r.drillable for r in rows}
    # same-host manager link is drillable; cross-host photo link is not.
    drillable = [r for r in rows if r.drillable]
    assert len(drillable) == 1 and 'manager' in drillable[0].label
    assert True in by_drillable and False in by_drillable


def test_build_rows_scalar_single_row():
    rows = tui_nav.build_rows('scalar', 'OK')
    assert len(rows) == 1 and not rows[0].drillable


def test_build_rows_object_caps_keys_with_sentinel():
    payload = {f'k{i}': i for i in range(tui_nav.MAX_KEYS + 3)}
    rows = tui_nav.build_rows('object', payload)
    assert len(rows) == tui_nav.MAX_KEYS + 1
    assert rows[-1].dim and 'more keys' in rows[-1].label


# ---------------------------------------------------------------------------
# next_path — three id-shapes
# ---------------------------------------------------------------------------

def test_next_path_relative_appends():
    assert tui_nav.next_path('me', 'messages') == 'me/messages'
    assert tui_nav.next_path('', 'users') == 'users'


def test_next_path_absolute_url_verbatim():
    url = 'https://graph.microsoft.com/v1.0/users/x/manager'
    assert tui_nav.next_path('users', url) == url


def test_next_path_arm_absolute_id_replaces():
    # ARM ids are absolute paths — they replace, never append.
    assert tui_nav.next_path('subscriptions', '/subscriptions/aaaa') == '/subscriptions/aaaa'


# ---------------------------------------------------------------------------
# _tui_get — curses-safe error mapping
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('exc,kind', [
    (AuthExpiredError('x'), 'auth'),
    (ScopeInsufficientError('x'), 'scope'),
    (NotFoundError('x'), 'notfound'),
    (RateLimitedError('x'), 'ratelimit'),
    (NetworkError('x'), 'error'),
    (InternalError('x'), 'error'),
])
def test_tui_get_maps_errors_without_raising(monkeypatch, exc, kind):
    def boom(*a, **k):
        raise exc
    monkeypatch.setattr(tui_nav._http, 'request', boom)
    status, msg = tui_nav._tui_get('https://x/y', 'tok')
    assert status == kind
    assert isinstance(msg, str)


def test_tui_get_ok_carries_headers(monkeypatch):
    class Resp:
        status = 200
        headers = {'X-Test': '1'}
        bytes = b'{"value": []}'
    monkeypatch.setattr(tui_nav._http, 'request', lambda *a, **k: Resp())
    status, result = tui_nav._tui_get('https://x/y', 'tok')
    assert status == 'ok'
    assert result.headers['X-Test'] == '1'
    assert result.body == b'{"value": []}'


# ---------------------------------------------------------------------------
# _fetch_page — the three continuation shapes
# ---------------------------------------------------------------------------

def _fake_ok(result):
    return lambda url, token, *, debug=False: ('ok', result)


def test_fetch_page_odata_cursor(monkeypatch, make_result, graph_collection):
    monkeypatch.setattr(tui_nav, '_tui_get', _fake_ok(make_result(graph_collection)))
    kind, payload, cursor = tui_nav._fetch_page('graph', 'https://g/users', 'tok')
    assert kind == 'collection'
    assert cursor == graph_collection['@odata.nextLink']


def test_fetch_page_arm_bare_nextlink(monkeypatch, make_result, arm_subscriptions):
    monkeypatch.setattr(tui_nav, '_tui_get', _fake_ok(make_result(arm_subscriptions)))
    kind, payload, cursor = tui_nav._fetch_page('azure', 'https://m/subscriptions', 'tok')
    assert kind == 'collection'
    assert cursor == arm_subscriptions['nextLink']


def test_fetch_page_devops_header_case_insensitive(monkeypatch, make_result, devops_continuation):
    payload, headers = devops_continuation
    result = make_result(payload, headers=headers)
    monkeypatch.setattr(tui_nav, '_tui_get', _fake_ok(result))
    url = 'https://app.vssps.visualstudio.com/_apis/projects'
    kind, _, cursor = tui_nav._fetch_page('devops', url, 'tok')
    assert cursor == f'{url}?continuationToken=CT-TOKEN-42'


def test_fetch_page_devops_no_cursor_when_header_absent(monkeypatch, make_result):
    monkeypatch.setattr(tui_nav, '_tui_get', _fake_ok(make_result({'value': []})))
    _, _, cursor = tui_nav._fetch_page('devops', 'https://x/_apis', 'tok')
    assert cursor is None


def test_fetch_page_propagates_failure(monkeypatch):
    monkeypatch.setattr(tui_nav, '_tui_get', lambda *a, **k: ('auth', 'auth expired (401)'))
    kind, payload, cursor = tui_nav._fetch_page('graph', 'https://g/me', 'tok')
    assert kind == 'auth'
    assert cursor is None
    assert isinstance(payload, str)


# ---------------------------------------------------------------------------
# Graph prefix index + template normalization + scope hints
# ---------------------------------------------------------------------------

def test_prefix_index_literal_vs_template_collision(monkeypatch):
    # /users, /users/me, /users/{id}, /users/{id}/manager:
    # children of `users` are exactly {me, {id}}; manager belongs to
    # `users/{id}`, never bubbles up to `users`.
    monkeypatch.setattr(
        tui_nav, 'all_paths',
        lambda endpoint='v1.0': ['/users', '/users/me', '/users/{id}', '/users/{id}/manager'],
    )
    index = tui_nav.build_prefix_index()
    children = tui_nav.completions_for('users', index)
    assert sorted(children) == ['me', '{id}']
    assert 'manager' not in children


def test_template_normalization_folds_concrete_id(monkeypatch):
    monkeypatch.setattr(
        tui_nav, 'all_paths',
        lambda endpoint='v1.0': [
            '/me', '/me/messages', '/me/messages/{id}', '/me/messages/{id}/attachments',
        ],
    )
    index = tui_nav.build_prefix_index()
    # A concrete message id folds to {id}, so completions resolve to its children.
    children = tui_nav.completions_for(
        'me/messages/AAMkAGI2abcdefghijklmnopqrstuvwxyz0123456789', index)
    assert children == ['attachments']


def test_completions_for_none_index_is_empty():
    assert tui_nav.completions_for('anything', None) == []


def test_scope_hint_reports_missing(monkeypatch):
    monkeypatch.setattr(tui_nav, 'required_scopes', lambda verb, path: ['Mail.Read', 'User.Read'])
    required, missing = tui_nav.scope_hint('me/messages', {'User.Read'})
    assert required == ['Mail.Read', 'User.Read']
    assert missing == ['Mail.Read']
