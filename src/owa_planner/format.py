"""Human-readable Planner formatting for --pretty mode.

Stdout-only; callers decide whether to emit this or raw JSON.
"""
from owa_core.format import pad, truncate

_DONE_MARK = '[x]'
_OPEN_MARK = '[ ]'


def format_plans_pretty(plans):
    if not plans:
        return 'No plans found.'
    return '\n'.join(
        f"{pad(p.get('title') or '', 40)}  {p.get('id') or ''}" for p in plans
    )


def format_buckets_pretty(buckets):
    if not buckets:
        return 'No buckets found.'
    return '\n'.join(
        f"{pad(b.get('name') or '', 30)}  {b.get('id') or ''}" for b in buckets
    )


def format_tasks_pretty(tasks):
    if not tasks:
        return 'No tasks found.'
    out = []
    for t in tasks:
        mark = _DONE_MARK if t.get('status') == 'Completed' else _OPEN_MARK
        title = pad(truncate(t.get('title') or '', 44), 44)
        bits = [f"{t.get('percentComplete') or 0:>3}%"]
        if t.get('due'):
            bits.append(f"due {t['due']}")
        label = t.get('priorityLabel')
        if label and label != 'medium':
            bits.append(f'!{label}')
        out.append(f"{mark} {title}  {'  '.join(bits)}".rstrip())
    return '\n'.join(out)


def format_task_pretty(task, detail):
    lines = [task.get('title') or '']
    lines.append(f"  status: {task.get('status') or ''} ({task.get('percentComplete') or 0}%)")
    if task.get('due'):
        lines.append(f"  due: {task['due']}")
    if task.get('priorityLabel'):
        lines.append(f"  priority: {task['priorityLabel']}")
    assignees = task.get('assignedTo') or []
    if assignees:
        lines.append(f"  assigned: {len(assignees)} ({', '.join(assignees)})")
    detail = detail or {}
    if detail.get('description'):
        lines.append(f"  description: {truncate(detail['description'], 200)}")
    for item in detail.get('checklist') or []:
        mark = _DONE_MARK if item.get('isChecked') else _OPEN_MARK
        lines.append(f"    {mark} {item.get('title') or ''}")
    return '\n'.join(lines)
