"""Tests for owa_planner.format (--pretty rendering)."""

from owa_planner import format as fmt


def test_format_plans_pretty():
    assert 'No plans' in fmt.format_plans_pretty([])
    out = fmt.format_plans_pretty([{'title': 'Team', 'id': 'p1'}])
    assert 'Team' in out and 'p1' in out


def test_format_buckets_pretty():
    assert 'No buckets' in fmt.format_buckets_pretty([])
    out = fmt.format_buckets_pretty([{'name': 'Doing', 'id': 'b1'}])
    assert 'Doing' in out and 'b1' in out


def test_format_tasks_pretty():
    assert 'No tasks' in fmt.format_tasks_pretty([])
    out = fmt.format_tasks_pretty([
        {'title': 'A', 'status': 'Completed', 'percentComplete': 100,
         'due': '2026-06-15', 'priorityLabel': 'urgent'},
        {'title': 'B', 'status': 'NotStarted', 'percentComplete': 0,
         'priorityLabel': 'medium'},
    ])
    assert '[x]' in out
    assert '[ ]' in out
    assert 'due 2026-06-15' in out
    assert '!urgent' in out
    assert '!medium' not in out  # medium priority is suppressed as the default


def test_format_task_pretty():
    out = fmt.format_task_pretty(
        {'title': 'A', 'status': 'InProgress', 'percentComplete': 50,
         'due': '2026-06-15', 'priorityLabel': 'important', 'assignedTo': ['u1']},
        {'description': 'desc', 'checklist': [{'title': 'step', 'isChecked': True}]},
    )
    assert out.splitlines()[0] == 'A'
    assert 'status: InProgress (50%)' in out
    assert 'due: 2026-06-15' in out
    assert 'priority: important' in out
    assert 'assigned: 1' in out
    assert '[x] step' in out


def test_format_task_pretty_minimal():
    out = fmt.format_task_pretty({'title': 'Bare', 'status': 'NotStarted'}, {})
    assert out.splitlines()[0] == 'Bare'
    assert 'status: NotStarted (0%)' in out
