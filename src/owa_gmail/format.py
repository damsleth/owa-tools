"""--pretty rendering for owa-gmail."""
from datetime import datetime


def _when(ms):
    if not ms:
        return ''
    return datetime.fromtimestamp(ms / 1000).strftime('%Y-%m-%d %H:%M')


def format_messages_pretty(rows):
    if not rows:
        return '(no messages)'
    lines = []
    for m in rows:
        unread = '*' if 'UNREAD' in (m.get('label_ids') or []) else ' '
        subject = m.get('subject') or m.get('snippet') or '(no subject)'
        lines.append(f"{unread} {_when(m.get('internal_date_ms'))}  {m.get('from', '')[:40]:<40}  {subject}")
        lines.append(f"    {m.get('id')}")
    return '\n'.join(lines)


def format_message_pretty(m):
    lines = [
        f"Subject: {m.get('subject', '')}",
        f"From:    {m.get('from', '')}",
        f"To:      {m.get('to', '')}",
    ]
    if m.get('cc'):
        lines.append(f"Cc:      {m['cc']}")
    lines.append(f"Date:    {m.get('date', '')}")
    lines.append(f"Id:      {m.get('id', '')}")
    for a in m.get('attachments') or []:
        lines.append(f"Attach:  {a['filename']} ({a.get('size') or 0} bytes)  id={a['attachment_id']}")
    lines += ['', m.get('body_plain') or m.get('snippet') or '']
    return '\n'.join(lines)


def format_labels_pretty(rows):
    if not rows:
        return '(no labels)'
    width = max(len(r['name']) for r in rows)
    return '\n'.join(f"{r['name']:<{width}}  {r['type']:<6}  {r['id']}" for r in rows)
