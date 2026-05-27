"""Human-readable task formatting for --pretty mode.

Stdout-only; callers decide whether to emit this or raw JSON.
"""
from owa_core.format import pad

_DONE_MARK = '[x]'
_OPEN_MARK = '[ ]'
_IMPORTANCE_MARK = {'High': '!', 'Low': '·'}


def format_tasks_pretty(tasks):
    """Build a multiline checklist view. Caller prints it."""
    if not tasks:
        return 'No tasks found.'
    out = []
    for t in tasks:
        done = (t.get('status') == 'Completed')
        mark = _DONE_MARK if done else _OPEN_MARK
        imp = _IMPORTANCE_MARK.get(t.get('importance') or '', ' ')
        subject = pad(t.get('subject') or '', 40)
        bits = []
        if t.get('due'):
            bits.append(f"due {t['due']}")
        cats = t.get('categories') or []
        if cats:
            bits.append(f"[{', '.join(cats)}]")
        suffix = ('  ' + '  '.join(bits)) if bits else ''
        out.append(f'{mark} {imp} {subject}{suffix}'.rstrip())
    return '\n'.join(out)


def format_folders_pretty(folders):
    if not folders:
        return 'No task folders found.'
    out = []
    for f in folders:
        star = '* ' if f.get('default') else '  '
        out.append(f"{star}{f.get('name') or ''}")
    return '\n'.join(out)
