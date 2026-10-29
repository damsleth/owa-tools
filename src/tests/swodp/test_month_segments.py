"""Weeks across a month boundary: rows scoped to a month segment.

Week 44 2026 (26 Oct - 1 Nov): Monday-Saturday are October (scope 0-5),
Sunday is November (scope 6). Each segment owns only the cards whose hours
fall inside it, and a card one row took is never reused by another.
"""
from types import SimpleNamespace

import pytest

from owa_core.errors import UsageError
from owa_swodp import service

SESSION = SimpleNamespace(user='a@example.invalid')
WEEK = '2026-10-26'
OCT, NOV = list(range(6)), [6]
# Card IDs are real-shaped: the pre-delete recheck validates them
OCT_ID, NOV_ID, ZERO_ID, SPAN_ID = ('a' * 32, 'b' * 32, 'c' * 32, 'd' * 32)


def card(sys_id, *, state='Pending', **days):
    return {'sys_id': sys_id, 'task.number': 'T12345', 'state': state, **{k: str(v) for k, v in days.items()}}


def stub(monkeypatch, existing):
    calls = []
    created = []

    def request(session, method, table, **kwargs):
        calls.append((method, kwargs.get('sys_id'), kwargs.get('body')))
        if method == 'GET' and kwargs.get('params', {}).get('sysparm_limit') == '200':
            return [dict(c) for c in existing]
        if table == 'task':
            return [{'sys_id': 'task'}]
        if table == 'resource_allocation':
            return []
        if method == 'POST':
            created.append(f'new{len(created)}')
            return {'sys_id': created[-1]}
        if method == 'GET' and kwargs.get('sys_id'):
            match = next((c for c in existing if c['sys_id'] == kwargs['sys_id']), None)
            return dict(match) if match else {'comments': 'saved'}
        return {}

    monkeypatch.setattr(service.api, 'request', request)
    return calls


def row(scope, days, **extra):
    return {'taskNumber': 'T12345', 'days': days, 'description': 'work', 'scope': scope, **extra}


def mutations(calls):
    return [(m, sys_id) for m, sys_id, _ in calls if m in ('PATCH', 'DELETE', 'POST')]


def test_each_segment_patches_its_own_card(monkeypatch):
    calls = stub(monkeypatch, [card(NOV_ID, sunday=4), card(OCT_ID, monday=8)])
    service.write_week(SESSION, WEEK, [
        row(OCT, [7.5, 0, 0, 0, 0, 0, 0]),
        row(NOV, [0, 0, 0, 0, 0, 0, 2]),
    ])
    patches = {sys_id: body for m, sys_id, body in calls if m == 'PATCH' and 'monday' in (body or {})}
    assert patches[OCT_ID]['monday'] == '7.5'
    assert patches[NOV_ID]['sunday'] == '2'


def test_zero_card_is_claimed_once(monkeypatch):
    calls = stub(monkeypatch, [card(ZERO_ID)])
    results = service.write_week(SESSION, WEEK, [
        row(OCT, [8, 0, 0, 0, 0, 0, 0]),
        row(NOV, [0, 0, 0, 0, 0, 0, 3]),
    ])
    assert [r['action'] for r in results] == ['updated', 'created']
    assert ('PATCH', ZERO_ID) in mutations(calls)


def test_spanning_card_belongs_to_no_segment(monkeypatch):
    calls = stub(monkeypatch, [card(SPAN_ID, monday=4, sunday=4)])
    service.write_week(SESSION, WEEK, [row(OCT, [8, 0, 0, 0, 0, 0, 0], remove=True)])
    assert not any(m == 'DELETE' for m, _ in mutations(calls))


def test_scoped_remove_deletes_only_its_month(monkeypatch):
    calls = stub(monkeypatch, [card(OCT_ID, monday=8), card(NOV_ID, sunday=4)])
    service.write_week(SESSION, WEEK, [row(NOV, [0] * 7, remove=True)])
    assert [x for x in mutations(calls) if x[0] == 'DELETE'] == [('DELETE', NOV_ID)]


def test_split_groups_per_segment_replace_only_their_cards(monkeypatch):
    calls = stub(monkeypatch, [card(OCT_ID, monday=8), card(NOV_ID, sunday=4)])
    results = service.write_week(SESSION, WEEK, [
        row(OCT, [4, 0, 0, 0, 0, 0, 0], split=True),
        row(OCT, [4, 0, 0, 0, 0, 0, 0], split=True, description='more'),
        row(NOV, [0, 0, 0, 0, 0, 0, 4], split=True),
    ])
    assert [r['action'] for r in results] == ['created', 'created', 'deleted', 'created', 'deleted']
    assert [sys_id for m, sys_id in mutations(calls) if m == 'DELETE'] == [OCT_ID, NOV_ID]


def test_split_and_plain_may_share_identity_in_different_months(monkeypatch):
    stub(monkeypatch, [card(OCT_ID, monday=8), card(NOV_ID, sunday=4)])
    results = service.write_week(SESSION, WEEK, [
        row(OCT, [4, 0, 0, 0, 0, 0, 0], split=True),
        row(NOV, [0, 0, 0, 0, 0, 0, 2]),
    ])
    assert {r['action'] for r in results} == {'created', 'updated', 'deleted'}


def test_overlapping_split_and_plain_refused_before_any_write(monkeypatch):
    calls = stub(monkeypatch, [card(OCT_ID, monday=8)])
    with pytest.raises(UsageError, match='same identity and days'):
        service.write_week(SESSION, WEEK, [
            row(OCT, [4, 0, 0, 0, 0, 0, 0], split=True),
            {'taskNumber': 'T12345', 'days': [4, 0, 0, 0, 0, 0, 0], 'description': 'whole week'},
        ])
    assert mutations(calls) == []


@pytest.mark.parametrize('scope', [[], [7], [0, 0], [True], 'monday', list(range(8))])
def test_invalid_scope_rejected(scope):
    with pytest.raises(UsageError, match='scope'):
        service.validate_write_rows([row(scope, [0] * 7)])


def test_hours_outside_scope_rejected():
    with pytest.raises(UsageError, match='outside its scope'):
        service.validate_write_rows([row(NOV, [8, 0, 0, 0, 0, 0, 0])])
