"""Planner JSON shaping: normalize Microsoft Graph /planner responses.

owa-planner talks to the Graph `/planner` surface (plannerPlan, plannerBucket,
plannerTask, plannerTaskDetails), which returns camelCase. We normalize into a
stable lowercase wire shape on read. Planner date fields (dueDateTime,
startDateTime, completedDateTime, createdDateTime) are ISO-8601 UTC; we surface
the local date (YYYY-MM-DD).

v1 is read-only. Writes are deferred: Planner PATCH requires the exact
`@odata.etag` in an `If-Match` header and the etag rotates on every write -
see AGENTS.md.
"""
from datetime import datetime, timezone

from owa_core.format import date_part

# User-facing --status filter values mapped to the status_for() vocabulary.
STATUS_ALIASES = {
    'notstarted': 'NotStarted',
    'not-started': 'NotStarted',
    'inprogress': 'InProgress',
    'in-progress': 'InProgress',
    'started': 'InProgress',
    'completed': 'Completed',
    'done': 'Completed',
}
_STATUS_WIRE = {'NotStarted', 'InProgress', 'Completed'}


def status_for(pct):
    """Derive a status label from percentComplete (Planner: 0 / 1-99 / 100)."""
    try:
        pct = int(pct)
    except (TypeError, ValueError):
        return ''
    if pct >= 100:
        return 'Completed'
    if pct <= 0:
        return 'NotStarted'
    return 'InProgress'


def normalize_status(value):
    """Map a user --status value to the status_for() vocabulary, or None."""
    if not value:
        return None
    if value in _STATUS_WIRE:
        return value
    return STATUS_ALIASES.get(value.lower())


def priority_label(value):
    """Planner priority int -> label. Microsoft mapping: 0-1 urgent, 2-4
    important, 5-7 medium, 8-10 low."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return ''
    if n <= 1:
        return 'urgent'
    if n <= 4:
        return 'important'
    if n <= 7:
        return 'medium'
    return 'low'


def _local_date(iso):
    """Local YYYY-MM-DD from a Graph ISO-8601 datetime (UTC, trailing Z), or ''.

    A naive datetime is treated as UTC. On parse failure the bare date prefix
    of the raw string is returned.
    """
    if not iso:
        return ''
    clean = iso.strip()
    if clean.endswith('Z'):
        clean = clean[:-1] + '+00:00'
    try:
        dt = datetime.fromisoformat(clean)
    except ValueError:
        return date_part(iso)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone().strftime('%Y-%m-%d')


def normalize_plan(plan):
    container = plan.get('container') or {}
    return {
        'id': plan.get('id'),
        'title': plan.get('title'),
        'owner': plan.get('owner') or container.get('containerId'),
        'created': _local_date(plan.get('createdDateTime') or ''),
    }


def normalize_plans(response):
    return [normalize_plan(p) for p in response.get('value', [])]


def normalize_bucket(bucket):
    return {
        'id': bucket.get('id'),
        'name': bucket.get('name'),
        'planId': bucket.get('planId'),
        'orderHint': bucket.get('orderHint'),
    }


def normalize_buckets(response):
    return [normalize_bucket(b) for b in response.get('value', [])]


def normalize_task(task):
    pct = task.get('percentComplete')
    pct = pct if isinstance(pct, int) else 0
    assignments = task.get('assignments') or {}
    return {
        'id': task.get('id'),
        'planId': task.get('planId'),
        'bucketId': task.get('bucketId'),
        'title': task.get('title'),
        'status': status_for(pct),
        'percentComplete': pct,
        'priority': task.get('priority'),
        'priorityLabel': priority_label(task.get('priority')),
        'due': _local_date(task.get('dueDateTime') or ''),
        'start': _local_date(task.get('startDateTime') or ''),
        'completed': _local_date(task.get('completedDateTime') or ''),
        'created': _local_date(task.get('createdDateTime') or ''),
        'assignedTo': list(assignments.keys()),
        'checklistItemCount': task.get('checklistItemCount') or 0,
        'activeChecklistItemCount': task.get('activeChecklistItemCount') or 0,
        'referenceCount': task.get('referenceCount') or 0,
        'hasDescription': bool(task.get('hasDescription')),
    }


def normalize_tasks(response):
    return [normalize_task(t) for t in response.get('value', [])]


def normalize_task_detail(detail):
    """Flatten plannerTaskDetails: checklist + references are URL/id-keyed maps."""
    checklist = [
        {'title': item.get('title'), 'isChecked': bool(item.get('isChecked'))}
        for item in (detail.get('checklist') or {}).values()
        if isinstance(item, dict)
    ]
    references = [
        {'alias': ref.get('alias'), 'url': key}
        for key, ref in (detail.get('references') or {}).items()
        if isinstance(ref, dict)
    ]
    return {
        'description': detail.get('description') or '',
        'checklist': checklist,
        'references': references,
        'previewType': detail.get('previewType'),
    }
