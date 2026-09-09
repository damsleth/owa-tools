from types import SimpleNamespace

import pytest

from owa_core.errors import ConflictError, NetworkError, NotFoundError
from owa_swodp import service

SESSION = SimpleNamespace(user='a@example.invalid')
ORIGINAL = {'sys_id':'a'*32, 'task.number':'T12345', 'state':'Pending', 'comments':'original hours', 'monday':'8'}
ROWS = [{'taskNumber':'T12345', 'days':[4,0,0,0,0,0,0], 'description':desc, 'split':True} for desc in ('one','two')]


def stub(monkeypatch, *, failure=None):
    calls = []
    created = []

    def request(session, method, table, **kwargs):
        calls.append((method, table, kwargs.get('sys_id')))
        if method == 'GET' and kwargs.get('params', {}).get('sysparm_limit') == '200':
            return [ORIGINAL.copy()]
        if table == 'task':
            if failure == 'missing-task':
                return []
            if failure == 'task-error':
                raise NetworkError('lookup failed')
            return [{'sys_id':'task'}]
        if table == 'resource_allocation':
            return []
        if method == 'POST':
            if failure == 'create-second' and created:
                raise NetworkError('second POST outcome unknown')
            created.append(str(len(created)))
            return {'sys_id':created[-1]}
        if method == 'PATCH' and failure == 'patch':
            raise NetworkError('patch failed')
        if method == 'GET' and kwargs.get('sys_id') == ORIGINAL['sys_id']:
            return {**ORIGINAL, 'state':'Submitted' if failure == 'state' else 'Pending'}
        if method == 'GET':
            return {'comments':'' if failure == 'verify' else 'saved'}
        if method == 'DELETE' and failure == 'delete':
            raise NetworkError('delete outcome unknown')
        return {}

    monkeypatch.setattr(service.api, 'request', request)
    return calls, created


@pytest.mark.parametrize('failure,error', [('missing-task',NotFoundError),('task-error',NetworkError)])
def test_split_preflight_failure_never_mutates(monkeypatch, failure, error):
    calls, _ = stub(monkeypatch, failure=failure)
    with pytest.raises(error):
        service.write_week(SESSION, '2026-09-07', ROWS)
    assert all(method == 'GET' for method, _, _ in calls)


@pytest.mark.parametrize('failure', ['create-second','patch','verify','state'])
def test_partial_replacement_preserves_original_and_reports_progress(monkeypatch, failure):
    calls, created = stub(monkeypatch, failure=failure)
    results = service.write_week(SESSION, '2026-09-07', ROWS)
    assert not any(method == 'DELETE' for method, _, _ in calls)
    assert results[-1]['action'] == 'failed'
    assert results[-1]['original_cards'] == [ORIGINAL]
    assert results[-1]['replacement_ids'] == created


def test_success_creates_verifies_and_only_then_deletes(monkeypatch):
    calls, created = stub(monkeypatch)
    results = service.write_week(SESSION, '2026-09-07', ROWS)
    assert [r['action'] for r in results] == ['created','created','deleted']
    assert calls[-1] == ('DELETE','time_card', ORIGINAL['sys_id'])
    assert calls[-2] == ('GET','time_card', ORIGINAL['sys_id'])
    assert [r['sys_id'] for r in results[:2]] == created


def test_delete_failure_keeps_snapshot_and_ids(monkeypatch):
    _, created = stub(monkeypatch, failure='delete')
    results = service.write_week(SESSION, '2026-09-07', ROWS)
    assert results[-1]['action'] == 'failed'
    assert results[-1]['replacement_ids'] == created
    assert results[-1]['original_cards'] == [ORIGINAL]


def test_locked_split_refuses_to_create_duplicates(monkeypatch):
    monkeypatch.setattr(service.api, 'request', lambda *a, **k: [{**ORIGINAL, 'state':'Approved'}])
    with pytest.raises(ConflictError):
        service.write_week(SESSION, '2026-09-07', ROWS)
