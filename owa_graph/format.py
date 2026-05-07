"""Pretty-printers for common Graph response shapes.

Graph paginates collections under `value`, with `@odata.nextLink` for
continuation. We surface a small handful of well-known shapes (users,
groups, messages, drive items) as compact tables; everything else falls
through to indented JSON so `--pretty` is always at least a little
nicer than the default single-line output.
"""
import json


def _pad(s, width):
    s = str(s) if s is not None else ''
    if len(s) >= width:
        return s
    return s + ' ' * (width - len(s))


def _looks_like_users(items):
    return all(isinstance(i, dict) and ('displayName' in i or 'userPrincipalName' in i) for i in items)


def _looks_like_groups(items):
    # Groups carry `mailEnabled` (Boolean) which neither users, teams, nor
    # channels have. Cheapest unambiguous discriminator.
    return all(isinstance(i, dict) and 'mailEnabled' in i for i in items)


def _looks_like_channels(items):
    # Channels: displayName + a teams.microsoft.com web URL. The webUrl is
    # how we tell channels apart from teams (which only sometimes carry
    # webUrl, and never with that host).
    if not items:
        return False
    for i in items:
        if not (isinstance(i, dict) and 'displayName' in i):
            return False
        url = i.get('webUrl') or ''
        if 'teams.microsoft.com' not in url:
            return False
    return True


def _looks_like_teams(items):
    # Teams: displayName + description, no mailEnabled (groups), no
    # userPrincipalName (users), no teams.microsoft.com webUrl (channels),
    # no appId (applications also carry `description: null`). Reordering
    # alone isn't enough - belt-and-suspenders so the detector can't
    # reclaim applications if dispatch order changes later.
    return all(
        isinstance(i, dict)
        and 'displayName' in i
        and 'description' in i
        and 'mailEnabled' not in i
        and 'userPrincipalName' not in i
        and 'appId' not in i
        for i in items
    )


def _looks_like_drives(items):
    # Every Graph drive carries `driveType` (personal | business |
    # documentLibrary). Unique enough to discriminate.
    return all(
        isinstance(i, dict) and i.get('driveType') in {
            'personal', 'business', 'documentLibrary',
        }
        for i in items
    )


def _looks_like_sites(items):
    # SharePoint site: displayName + a sharepoint.com webUrl. Drives
    # also live on sharepoint.com, but they get caught earlier by the
    # driveType detector.
    if not items:
        return False
    for i in items:
        if not (isinstance(i, dict) and 'displayName' in i):
            return False
        url = i.get('webUrl') or ''
        if 'sharepoint.com' not in url:
            return False
    return True


def _looks_like_calendars(items):
    # Outlook calendar: `name` + `canEdit` (Boolean). `canEdit` doesn't
    # appear on any other shape we render.
    return all(
        isinstance(i, dict) and 'name' in i and isinstance(i.get('canEdit'), bool)
        for i in items
    )


_UUID_LEN = 36


def _is_uuid_shape(s):
    # Cheap UUID heuristic without importing re. Graph appId is canonical
    # 8-4-4-4-12 hex; we don't need to validate hex chars - the dash
    # positions alone are enough to distinguish appId from a free-form
    # id string.
    return (isinstance(s, str)
            and len(s) == _UUID_LEN
            and s[8] == s[13] == s[18] == s[23] == '-')


def _looks_like_applications(items):
    # Graph application objects: displayName + appId in UUID form. The
    # appId shape is what tells us this isn't a user (whose `id` is also
    # a UUID but doesn't sit in `appId`).
    return all(
        isinstance(i, dict)
        and 'displayName' in i
        and _is_uuid_shape(i.get('appId'))
        for i in items
    )


def _looks_like_audit_logs(items):
    # directoryAudits / signIns: both carry `activityDateTime` +
    # `activityDisplayName`. Unique enough to claim the table.
    return all(
        isinstance(i, dict)
        and 'activityDateTime' in i
        and 'activityDisplayName' in i
        for i in items
    )


def _looks_like_planner_tasks(items):
    # Every Planner task carries `percentComplete` (int 0-100). No other
    # Graph shape we render uses that field.
    return all(
        isinstance(i, dict)
        and 'title' in i
        and isinstance(i.get('percentComplete'), int)
        for i in items
    )


def _looks_like_todo_tasks(items):
    # Microsoft To-Do task: `title` + a `status` enum ("notStarted",
    # "inProgress", "completed", "waitingOnOthers", "deferred").
    valid_status = {
        'notStarted', 'inProgress', 'completed', 'waitingOnOthers', 'deferred',
    }
    return all(
        isinstance(i, dict)
        and 'title' in i
        and i.get('status') in valid_status
        for i in items
    )


def _looks_like_messages(items):
    return all(
        isinstance(i, dict) and 'subject' in i and ('from' in i or 'sender' in i)
        for i in items
    )


def _looks_like_drive_items(items):
    return all(isinstance(i, dict) and 'name' in i and ('size' in i or 'folder' in i or 'file' in i) for i in items)


def _format_users(items):
    rows = [(i.get('displayName') or '',
             i.get('userPrincipalName') or i.get('mail') or '',
             i.get('id') or '') for i in items]
    if not rows:
        return '(no items)'
    name_w = max(len(r[0]) for r in rows)
    upn_w = max(len(r[1]) for r in rows)
    return '\n'.join(
        f'{_pad(n, name_w)}  {_pad(u, upn_w)}  {i}' for n, u, i in rows
    )


def _format_messages(items):
    rows = []
    for m in items:
        sender = m.get('from') or m.get('sender') or {}
        addr = (sender.get('emailAddress') or {}).get('address') or ''
        rows.append((
            m.get('receivedDateTime', '')[:16].replace('T', ' '),
            addr,
            m.get('subject') or '',
        ))
    if not rows:
        return '(no items)'
    date_w = max(len(r[0]) for r in rows)
    addr_w = min(max((len(r[1]) for r in rows), default=0), 32)
    return '\n'.join(
        f'{_pad(d, date_w)}  {_pad(a[:addr_w], addr_w)}  {s}'
        for d, a, s in rows
    )


def _format_groups(items):
    rows = [(
        i.get('displayName') or '',
        i.get('mail') or '',
        i.get('id') or '',
    ) for i in items]
    if not rows:
        return '(no items)'
    name_w = max(len(r[0]) for r in rows)
    mail_w = max(len(r[1]) for r in rows)
    return '\n'.join(
        f'{_pad(n, name_w)}  {_pad(m, mail_w)}  {i}' for n, m, i in rows
    )


def _format_teams(items):
    rows = [(
        i.get('displayName') or '',
        i.get('id') or '',
    ) for i in items]
    if not rows:
        return '(no items)'
    name_w = max(len(r[0]) for r in rows)
    return '\n'.join(
        f'{_pad(n, name_w)}  {i}' for n, i in rows
    )


def _format_channels(items):
    rows = [(
        i.get('displayName') or '',
        i.get('membershipType') or '',
        i.get('id') or '',
    ) for i in items]
    if not rows:
        return '(no items)'
    name_w = max(len(r[0]) for r in rows)
    type_w = max(len(r[1]) for r in rows)
    return '\n'.join(
        f'{_pad(n, name_w)}  {_pad(t, type_w)}  {i}' for n, t, i in rows
    )


def _format_drives(items):
    rows = [(
        i.get('name') or '',
        i.get('driveType') or '',
        i.get('id') or '',
    ) for i in items]
    if not rows:
        return '(no items)'
    name_w = max(len(r[0]) for r in rows)
    type_w = max(len(r[1]) for r in rows)
    return '\n'.join(
        f'{_pad(n, name_w)}  {_pad(t, type_w)}  {i}' for n, t, i in rows
    )


def _format_sites(items):
    rows = [(
        i.get('displayName') or '',
        i.get('webUrl') or '',
    ) for i in items]
    if not rows:
        return '(no items)'
    name_w = max(len(r[0]) for r in rows)
    return '\n'.join(
        f'{_pad(n, name_w)}  {u}' for n, u in rows
    )


def _format_calendars(items):
    rows = []
    for i in items:
        owner = ((i.get('owner') or {}).get('address')
                 or (i.get('owner') or {}).get('name')
                 or '')
        rows.append((
            i.get('name') or '',
            owner,
            i.get('id') or '',
        ))
    if not rows:
        return '(no items)'
    name_w = max(len(r[0]) for r in rows)
    owner_w = max(len(r[1]) for r in rows)
    return '\n'.join(
        f'{_pad(n, name_w)}  {_pad(o, owner_w)}  {i}' for n, o, i in rows
    )


def _format_applications(items):
    rows = [(
        i.get('displayName') or '',
        i.get('appId') or '',
    ) for i in items]
    if not rows:
        return '(no items)'
    name_w = max(len(r[0]) for r in rows)
    return '\n'.join(
        f'{_pad(n, name_w)}  {a}' for n, a in rows
    )


def _format_audit_logs(items):
    rows = []
    for i in items:
        when = (i.get('activityDateTime') or '')[:19].replace('T', ' ')
        actor = (
            (i.get('initiatedBy') or {})
            .get('user', {}).get('userPrincipalName')
            or (i.get('initiatedBy') or {}).get('app', {}).get('displayName')
            or ''
        )
        rows.append((
            when,
            actor,
            i.get('activityDisplayName') or '',
        ))
    if not rows:
        return '(no items)'
    when_w = max(len(r[0]) for r in rows)
    actor_w = min(max(len(r[1]) for r in rows), 40)
    return '\n'.join(
        f'{_pad(w, when_w)}  {_pad(a[:actor_w], actor_w)}  {act}'
        for w, a, act in rows
    )


def _format_planner_tasks(items):
    rows = []
    for i in items:
        due = (i.get('dueDateTime') or '')[:10]
        pct = i.get('percentComplete')
        pct_s = '' if pct is None else f'{pct}%'
        rows.append((
            i.get('title') or '',
            due,
            pct_s,
            i.get('id') or '',
        ))
    if not rows:
        return '(no items)'
    title_w = max(len(r[0]) for r in rows)
    due_w = max(len(r[1]) for r in rows) or 10
    pct_w = max(len(r[2]) for r in rows) or 4
    return '\n'.join(
        f'{_pad(t, title_w)}  {_pad(d, due_w)}  {_pad(p, pct_w)}  {i}'
        for t, d, p, i in rows
    )


def _format_todo_tasks(items):
    rows = []
    for i in items:
        due = ((i.get('dueDateTime') or {}).get('dateTime') or '')[:10]
        rows.append((
            i.get('title') or '',
            i.get('status') or '',
            due,
        ))
    if not rows:
        return '(no items)'
    title_w = max(len(r[0]) for r in rows)
    status_w = max(len(r[1]) for r in rows)
    return '\n'.join(
        f'{_pad(t, title_w)}  {_pad(s, status_w)}  {d}' for t, s, d in rows
    )


def _format_drive_items(items):
    rows = [(
        'd' if i.get('folder') else 'f',
        str(i.get('size') or ''),
        i.get('name') or '',
    ) for i in items]
    size_w = max(len(r[1]) for r in rows) if rows else 0
    return '\n'.join(
        f'{t}  {_pad(sz, size_w)}  {n}' for t, sz, n in rows
    ) or '(no items)'


def format_pretty(payload):
    """Best-effort pretty printer.

    Recognises Graph-style collection responses (`{value: [...]}`) for a
    few common shapes; otherwise indents the JSON. Always returns a
    string ready for `print()`."""
    if isinstance(payload, dict) and isinstance(payload.get('value'), list):
        items = payload['value']
        if items:
            # Order matters: more specific shapes first. `mailEnabled`,
            # `teams.microsoft.com` webUrl, and `description`-without-
            # mailEnabled discriminate the new shapes from `_looks_like_users`,
            # which would otherwise greedily match displayName-only items.
            if _looks_like_groups(items):
                return _format_groups(items)
            if _looks_like_drives(items):
                return _format_drives(items)
            if _looks_like_channels(items):
                return _format_channels(items)
            if _looks_like_applications(items):
                return _format_applications(items)
            if _looks_like_teams(items):
                return _format_teams(items)
            if _looks_like_sites(items):
                return _format_sites(items)
            if _looks_like_calendars(items):
                return _format_calendars(items)
            if _looks_like_planner_tasks(items):
                return _format_planner_tasks(items)
            if _looks_like_todo_tasks(items):
                return _format_todo_tasks(items)
            if _looks_like_audit_logs(items):
                return _format_audit_logs(items)
            if _looks_like_users(items):
                return _format_users(items)
            if _looks_like_messages(items):
                return _format_messages(items)
            if _looks_like_drive_items(items):
                return _format_drive_items(items)
    if isinstance(payload, (dict, list)):
        return json.dumps(payload, indent=2, ensure_ascii=False)
    return str(payload)
