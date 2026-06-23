"""Pure-function tests for owa_planner.plans (normalizers + helpers)."""

from owa_planner import plans


def test_status_for():
    assert plans.status_for(0) == 'NotStarted'
    assert plans.status_for(50) == 'InProgress'
    assert plans.status_for(100) == 'Completed'
    assert plans.status_for(None) == ''


def test_normalize_status():
    assert plans.normalize_status('done') == 'Completed'
    assert plans.normalize_status('in-progress') == 'InProgress'
    assert plans.normalize_status('Completed') == 'Completed'  # already wire form
    assert plans.normalize_status('bogus') is None
    assert plans.normalize_status('') is None


def test_priority_label():
    assert plans.priority_label(1) == 'urgent'
    assert plans.priority_label(3) == 'important'
    assert plans.priority_label(5) == 'medium'
    assert plans.priority_label(9) == 'low'
    assert plans.priority_label(None) == ''


def test_local_date_treats_naive_as_utc():
    # conftest pins TZ=UTC, so UTC in -> UTC out (no date drift).
    assert plans._local_date('2026-06-15T00:00:00Z') == '2026-06-15'
    assert plans._local_date('') == ''
    assert plans._local_date('not-a-date') == 'not-a-date'


def test_normalize_plan():
    p = plans.normalize_plan({
        'id': 'p1', 'title': 'Team', 'owner': 'g1',
        'createdDateTime': '2026-06-01T00:00:00Z',
    })
    assert p == {'id': 'p1', 'etag': None, 'title': 'Team', 'owner': 'g1', 'created': '2026-06-01'}


def test_normalize_plan_falls_back_to_container_id():
    p = plans.normalize_plan({'id': 'p1', 'title': 'T', 'container': {'containerId': 'g9'}})
    assert p['owner'] == 'g9'


def test_normalize_bucket():
    assert plans.normalize_bucket(
        {'id': 'b1', 'name': 'Doing', 'planId': 'p1', 'orderHint': 'x'}
    ) == {'id': 'b1', 'etag': None, 'name': 'Doing', 'planId': 'p1', 'orderHint': 'x'}


def test_normalize_task_flattens_fields():
    raw = {
        'id': 't1', 'planId': 'p1', 'bucketId': 'b1', 'title': 'Draft',
        'percentComplete': 50, 'priority': 5,
        'dueDateTime': '2026-06-15T00:00:00Z',
        'createdDateTime': '2026-06-01T00:00:00Z',
        'completedDateTime': None,
        'assignments': {'user-a': {}, 'user-b': {}},
        'checklistItemCount': 3, 'activeChecklistItemCount': 1,
        'referenceCount': 0, 'hasDescription': True,
    }
    t = plans.normalize_task(raw)
    assert t['id'] == 't1'
    assert t['status'] == 'InProgress'
    assert t['percentComplete'] == 50
    assert t['priorityLabel'] == 'medium'
    assert t['due'] == '2026-06-15'
    assert t['completed'] == ''
    assert sorted(t['assignedTo']) == ['user-a', 'user-b']
    assert t['checklistItemCount'] == 3
    assert t['hasDescription'] is True


def test_normalize_task_defaults_when_sparse():
    t = plans.normalize_task({'id': 't2', 'title': 'x'})
    assert t['status'] == 'NotStarted'
    assert t['percentComplete'] == 0
    assert t['assignedTo'] == []
    assert t['hasDescription'] is False


def test_normalize_task_detail():
    d = plans.normalize_task_detail({
        'description': 'hello',
        'checklist': {
            'c1': {'title': 'step 1', 'isChecked': True},
            'c2': {'title': 'step 2', 'isChecked': False},
        },
        'references': {'http%3A//x': {'alias': 'X', 'type': 'Other'}},
        'previewType': 'description',
    })
    assert d['description'] == 'hello'
    assert {'title': 'step 1', 'isChecked': True} in d['checklist']
    assert {'title': 'step 2', 'isChecked': False} in d['checklist']
    assert d['references'][0]['alias'] == 'X'
    assert d['previewType'] == 'description'
