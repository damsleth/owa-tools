"""Pretty-shape detectors + formatters for Planner and To-Do tasks.

Both share `title` so the discriminator has to come from a different
field: Planner uses `percentComplete` (int), To-Do uses `status` (enum).
"""
from owa_graph import format as fmt


# --- detectors -------------------------------------------------------------

def test_planner_detected_by_percent_complete():
    items = [{'title': 'A', 'percentComplete': 0, 'id': 'p1'}]
    assert fmt._looks_like_planner_tasks(items)
    assert not fmt._looks_like_todo_tasks(items)


def test_todo_detected_by_status_enum():
    items = [{'title': 'B', 'status': 'notStarted'}]
    assert fmt._looks_like_todo_tasks(items)
    assert not fmt._looks_like_planner_tasks(items)


def test_todo_rejects_unknown_status():
    items = [{'title': 'B', 'status': 'frobbed'}]
    assert not fmt._looks_like_todo_tasks(items)


def test_planner_requires_int_percent():
    # percentComplete must be int (Planner emits 0/50/100). A string
    # value is suspicious enough to skip the table.
    items = [{'title': 'A', 'percentComplete': '50'}]
    assert not fmt._looks_like_planner_tasks(items)


# --- formatters -----------------------------------------------------------

def test_format_pretty_planner_table():
    payload = {'value': [
        {'title': 'Ship v0.4', 'percentComplete': 50,
         'dueDateTime': '2026-06-01T00:00:00Z', 'id': 'p1'},
        {'title': 'Write docs', 'percentComplete': 0,
         'dueDateTime': None, 'id': 'p2'},
    ]}
    out = fmt.format_pretty(payload)
    assert 'Ship v0.4' in out
    assert '50%' in out
    assert '2026-06-01' in out
    assert 'p1' in out


def test_format_pretty_todo_table():
    payload = {'value': [
        {'title': 'Buy milk', 'status': 'notStarted',
         'dueDateTime': {'dateTime': '2026-05-05T00:00:00.0000000', 'timeZone': 'UTC'}},
        {'title': 'Refactor X', 'status': 'completed', 'dueDateTime': None},
    ]}
    out = fmt.format_pretty(payload)
    assert 'Buy milk' in out
    assert 'notStarted' in out
    assert '2026-05-05' in out
    assert 'completed' in out


def test_planner_routes_before_users():
    # Planner tasks have `title` not `displayName`, so users wouldn't
    # claim them anyway; this test just locks the dispatch order so a
    # future detector loosening can't silently regress it.
    payload = {'value': [
        {'title': 'A', 'percentComplete': 0, 'id': 'p1'},
    ]}
    out = fmt.format_pretty(payload)
    # planner formatter emits a percent column; users formatter wouldn't.
    assert '0%' in out
