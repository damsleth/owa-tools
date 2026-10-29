"""New project cards link the resource plan that covers the written week."""
from types import SimpleNamespace

from owa_core.errors import ScopeInsufficientError
from owa_swodp import service

SESSION = SimpleNamespace(user='a@example.invalid')
WEEK = '2026-10-26'


def alloc(plan, *, start='2026-01-01', end='2026-12-31', plan_state='Approved', state='Approved'):
    return {
        'resource_plan': {'value': plan, 'display_value': plan},
        'resource_plan.state': {'value': plan_state.lower(), 'display_value': plan_state},
        'start_date': {'value': start, 'display_value': 'x'},
        'end_date': {'value': end, 'display_value': 'x'},
        'state': {'value': state.lower(), 'display_value': state},
    }


def base_with(monkeypatch, allocations):
    def request(session, method, table, **kwargs):
        if table == 'task':
            return [{'sys_id': 'task'}]
        if isinstance(allocations, Exception):
            raise allocations
        return allocations

    monkeypatch.setattr(service.api, 'request', request)
    return service._project_base(SESSION, WEEK, 'T12345')


def test_skips_completed_plan_with_newest_end_date(monkeypatch):
    base = base_with(monkeypatch, [alloc('done', plan_state='Completed'), alloc('open')])
    assert base['resource_plan'] == 'open'


def test_skips_allocations_outside_the_week(monkeypatch):
    base = base_with(monkeypatch, [
        alloc('later', start='2026-11-02'), alloc('earlier', end='2026-10-25'), alloc('edge', end='2026-10-26'),
    ])
    assert base['resource_plan'] == 'edge'


def test_closed_allocation_state_is_skipped(monkeypatch):
    assert base_with(monkeypatch, [alloc('x', state='Cancelled'), alloc('y')])['resource_plan'] == 'y'


def test_no_covering_plan_creates_without_it(monkeypatch):
    base = base_with(monkeypatch, [alloc('old', end='2025-12-31')])
    assert 'resource_plan' not in base and base['task'] == 'task'


def test_forbidden_allocations_create_without_plan(monkeypatch):
    base = base_with(monkeypatch, ScopeInsufficientError('403'))
    assert 'resource_plan' not in base
