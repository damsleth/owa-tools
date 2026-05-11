"""Human-readable mail formatting for --pretty mode.

Two surfaces:
- format_messages_pretty: a list of messages, one per line.
- format_message_pretty: a single message - header block plus body.

Stdout-only output strings; callers decide whether to emit these or
raw JSON.
"""
from owa_core.format import date_part as _date_part
from owa_core.format import pad as _pad
from owa_core.format import time_part as _time_part
from owa_core.format import truncate as _truncate


def format_messages_pretty(messages):
    """Build a multiline table summarising messages.

    Columns: received-date, received-time, unread-marker, sender,
    subject, preview snippet. Sorted newest first.
    """
    if not messages:
        return 'No messages found.'
    rows = sorted(
        messages,
        key=lambda m: m.get('received') or '',
        reverse=True,
    )
    out = []
    for m in rows:
        date = _date_part(m.get('received') or '')
        time = _time_part(m.get('received') or '')
        marker = '*' if not m.get('is_read') else ' '
        flag = '!' if (m.get('flag') == 'Flagged') else ' '
        att = '@' if m.get('has_attachments') else ' '
        sender = _pad(_truncate(m.get('from') or '', 28), 28)
        subj = _pad(_truncate(m.get('subject') or '(no subject)', 40), 40)
        preview = _truncate(
            (m.get('preview') or '').replace('\r', ' ').replace('\n', ' '),
            60,
        )
        out.append(
            f'{date} {time} {marker}{flag}{att}  {sender}  {subj}  {preview}'
        )
    return '\n'.join(out)


def format_message_pretty(message):
    """Single-message rendering: header block then body.

    The body is printed verbatim (HTML or text - we don't strip HTML;
    that would need an HTML parser and we stay stdlib-rendering-only).
    """
    if not message:
        return 'No message.'
    lines = []
    for label, key in (
        ('From', 'from'),
        ('To', 'to'),
        ('Cc', 'cc'),
        ('Bcc', 'bcc'),
        ('Date', 'received'),
        ('Subject', 'subject'),
    ):
        value = message.get(key) or ''
        if value:
            lines.append(f'{label}: {value}')
    extras = []
    if message.get('flag') == 'Flagged':
        extras.append('flagged')
    if message.get('has_attachments'):
        extras.append('has attachments')
    if message.get('importance') and message['importance'].lower() != 'normal':
        extras.append(f"importance={message['importance'].lower()}")
    if extras:
        lines.append('  ' + ' / '.join(extras))
    lines.append('')
    lines.append(message.get('body') or '')
    return '\n'.join(lines)


def format_folders_pretty(folders):
    """Tabular folder listing: name, unread, total."""
    if not folders:
        return 'No folders.'
    width = max(len(f.get('name') or '') for f in folders)
    out = []
    for f in folders:
        name = _pad(f.get('name') or '', width)
        unread = f.get('unread') or 0
        total = f.get('total') or 0
        out.append(f'{name}  unread={unread}  total={total}')
    return '\n'.join(out)
