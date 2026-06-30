"""Task JSON shaping: normalize Outlook REST responses, build bodies.

owa-todo talks to the Outlook REST API v2.0 Tasks surface
(`me/taskfolders`, `me/tasks`), which returns PascalCase. We normalize
into lowercase-key shapes on read and emit PascalCase on write, matching
owa_cal's conventions.

To Do stores task date fields (DueDateTime, StartDateTime,
CompletedDateTime, ReminderDateTime) in UTC. We convert to the host's
local time on read; a naive datetime is therefore treated as UTC. Unlike
owa_cal we do not carry the full Windows-zone table here because To Do
does not return named Windows zones for these fields - see AGENTS.md.
"""
from datetime import date, datetime, timezone

from owa_core.format import date_part

# User-facing --status / --importance values mapped to the Outlook REST
# wire vocabulary (PascalCase). Anything already in the wire form passes
# through via the reverse lookup.
STATUS_ALIASES = {
    'notstarted': 'NotStarted',
    'not-started': 'NotStarted',
    'inprogress': 'InProgress',
    'in-progress': 'InProgress',
    'started': 'InProgress',
    'completed': 'Completed',
    'done': 'Completed',
    'waiting': 'WaitingOnOthers',
    'waitingonothers': 'WaitingOnOthers',
    'deferred': 'Deferred',
}
STATUS_WIRE = {v for v in STATUS_ALIASES.values()}

IMPORTANCE_ALIASES = {'low': 'Low', 'normal': 'Normal', 'high': 'High'}

# Minimal documented recurrence subset. To Do/Outlook REST wants a
# PatternedRecurrence {Pattern, Range}; we anchor an open-ended range at
# the task's start (the server fills it in) and only support the two
# everyday cadences. Anything else is a usage error.
RECURRENCE_PATTERNS = {
    'daily': {'Type': 'Daily', 'Interval': 1},
    'weekly': {'Type': 'Weekly', 'Interval': 1},
}


def normalize_status(value):
    """Map a user --status value to the wire vocabulary, or None."""
    if not value:
        return None
    if value in STATUS_WIRE:
        return value
    return STATUS_ALIASES.get(value.lower())


def normalize_importance(value):
    if not value:
        return None
    return IMPORTANCE_ALIASES.get(value.lower(), value)


def _parse_outlook_datetime(dt_str):
    clean = dt_str.strip()
    if clean.endswith('Z'):
        clean = clean[:-1] + '+00:00'
    if '.' in clean:
        prefix, rest = clean.split('.', 1)
        digits = []
        suffix_at = len(rest)
        for i, ch in enumerate(rest):
            if ch.isdigit():
                digits.append(ch)
            else:
                suffix_at = i
                break
        frac = ''.join(digits)[:6]
        suffix = rest[suffix_at:]
        clean = f'{prefix}.{frac}{suffix}' if frac else f'{prefix}{suffix}'
    return datetime.fromisoformat(clean)


def to_local(dt_str, tz_name=''):
    """Convert an Outlook task datetime string to local time.

    To Do returns these fields in UTC, so a naive datetime is treated as
    UTC. If the string carries its own offset we trust it. On any parse
    failure the raw string is returned unchanged.
    """
    del tz_name  # To Do task fields are UTC; tz name is informational only.
    if not dt_str:
        return ''
    try:
        dt = _parse_outlook_datetime(dt_str)
    except ValueError:
        return dt_str
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone().strftime('%Y-%m-%dT%H:%M:%S')


def _date_field(field):
    """Local date (YYYY-MM-DD) from a {DateTime, TimeZone} field, or ''."""
    field = field or {}
    return date_part(to_local(field.get('DateTime') or '', field.get('TimeZone') or ''))


def normalize_folder(folder):
    return {
        'id': folder.get('Id'),
        'name': folder.get('Name'),
        'default': bool(folder.get('IsDefaultFolder')),
    }


def normalize_folders(response):
    return [normalize_folder(f) for f in response.get('value', [])]


def normalize_task(task):
    """Flatten an Outlook REST task (PascalCase) into owa-todo's wire shape.

    Body is intentionally omitted (it arrives as HTML and is rarely
    needed in a list); fetch the raw task with owa-graph if required.
    """
    reminder = task.get('ReminderDateTime') or {}
    return {
        'id': task.get('Id'),
        'subject': task.get('Subject'),
        'status': task.get('Status'),
        'importance': task.get('Importance'),
        'due': _date_field(task.get('DueDateTime')),
        'start': _date_field(task.get('StartDateTime')),
        'completed': _date_field(task.get('CompletedDateTime')),
        'reminder': (
            to_local(reminder.get('DateTime') or '', reminder.get('TimeZone') or '')
            if task.get('IsReminderOn') else ''
        ),
        'categories': task.get('Categories') or [],
        'folderId': task.get('ParentFolderId'),
    }


def normalize_tasks(response):
    return [normalize_task(t) for t in response.get('value', [])]


def _due_datetime(date_value, tz):
    """Build a DueDateTime/StartDateTime object from a YYYY-MM-DD date.

    To Do treats due/start as a day; we anchor it at local midnight in
    the configured timezone, matching how the calendar tool emits dates.
    """
    return {'DateTime': f'{date_value}T00:00:00', 'TimeZone': tz or 'UTC'}


def _reminder_datetime(value, tz):
    """Build a ReminderDateTime object from an ISO datetime string.

    Accepts a bare `YYYY-MM-DDTHH:MM[:SS]` (anchored in the configured
    timezone). Reminders are a point in time, so IsReminderOn is set by
    the caller alongside this field.
    """
    return {'DateTime': value, 'TimeZone': tz or 'UTC'}


def normalize_recurrence(value):
    """Map a user --recurrence value to a PatternedRecurrence Pattern, or None."""
    if not value:
        return None
    return RECURRENCE_PATTERNS.get(value.lower())


def _recurrence_object(pattern, start, tz):
    """Wrap a recurrence Pattern in the PatternedRecurrence envelope.

    The Range anchors at `start` (or today's date if none) in the
    configured timezone; To Do treats an undated NoEnd range as open.
    """
    anchor = start or date.today().strftime('%Y-%m-%d')
    return {
        'Pattern': pattern,
        'Range': {'Type': 'NoEnd', 'StartDate': anchor, 'RecurrenceTimeZone': tz or 'UTC'},
    }


def build_task_json(subject, importance='', due='', start='', body_text='', tz='',
                    reminder='', recurrence=None, categories=None):
    """Build the POST body for creating an Outlook REST task."""
    out = {
        'Subject': subject,
        'Importance': normalize_importance(importance) or 'Normal',
    }
    if due:
        out['DueDateTime'] = _due_datetime(due, tz)
    if start:
        out['StartDateTime'] = _due_datetime(start, tz)
    if body_text:
        out['Body'] = {'ContentType': 'Text', 'Content': body_text}
    if reminder:
        out['ReminderDateTime'] = _reminder_datetime(reminder, tz)
        out['IsReminderOn'] = True
    if recurrence:
        out['Recurrence'] = _recurrence_object(recurrence, start, tz)
    if categories:
        out['Categories'] = list(categories)
    return out


def build_task_patch(fields, tz):
    """Build the PATCH body for updating a task.

    `fields` carries any of: subject, importance, status, body, due,
    start, reminder, recurrence, categories. Only provided keys land in
    the output - empty values are a caller bug, mirroring
    owa_cal.build_patch_json.
    """
    out = {}
    for key, val in fields.items():
        if key == 'subject':
            out['Subject'] = val
        elif key == 'importance':
            out['Importance'] = normalize_importance(val) or 'Normal'
        elif key == 'status':
            out['Status'] = normalize_status(val) or val
        elif key == 'body':
            out['Body'] = {'ContentType': 'Text', 'Content': val}
        elif key == 'due':
            out['DueDateTime'] = _due_datetime(val, tz)
        elif key == 'start':
            out['StartDateTime'] = _due_datetime(val, tz)
        elif key == 'reminder':
            out['ReminderDateTime'] = _reminder_datetime(val, tz)
            out['IsReminderOn'] = True
        elif key == 'recurrence':
            out['Recurrence'] = _recurrence_object(val, fields.get('start', ''), tz)
        elif key == 'categories':
            out['Categories'] = list(val)
    return out


def build_folder_json(name):
    """Build the POST/PATCH body for a task folder (To Do list)."""
    return {'Name': name}
