"""Normalize Halo ticket, action and attachment payloads.

Halo returns ~330 ticket fields, most of them null or empty. We keep every
field that carries a value (0 and False included) so "all metadata" stays
intact without the noise.

Inline screenshots in `details_html` / `note_html` are
`<img src="https://<host>/api/attachment/image?token=...">`. That URL is a
bearer credential (it works with no auth), so it never reaches output: the
src is rewritten to `halo-image:<n>` and the URL is kept only in memory
for `attachments --out`.
"""

import html
import re
from urllib.parse import parse_qs, urlsplit

from owa_core.errors import UsageError

_IMG_SRC_RE = re.compile(r'''(<img\b[^>]*?\bsrc=)(["'])(https?://[^"']*/api/attachment/image\?[^"']*)\2''', re.I)
_TAG_RE = re.compile(r'<[^>]+>')


def parse_ticket_ref(value):
    """`69296` or `https://<host>/ticket?id=69296` -> (id, host_or_None)."""
    value = value.strip()
    if value.isdigit():
        return int(value), None
    parts = urlsplit(value)
    ids = parse_qs(parts.query).get('id', [])
    if parts.netloc and ids and ids[0].isdigit():
        return int(ids[0]), parts.netloc
    raise UsageError(f'not a Halo ticket id or URL: {value!r}')


def _compact(obj):
    if isinstance(obj, dict):
        out = {}
        for key, value in obj.items():
            value = _compact(value)
            if value is None or value == '' or value == [] or value == {}:
                continue
            out[key] = value
        return out
    if isinstance(obj, list):
        return [_compact(v) for v in obj]
    return obj


def extract_images(markup, images, source):
    """Rewrite inline-image srcs to `halo-image:<n>`, appending to `images`."""
    if not markup:
        return markup

    def repl(match):
        url = match.group(3).replace('&amp;', '&')
        # Halo repeats the ticket body's images in the creation action.
        n = next((img['n'] for img in images if img['url'] == url), None)
        if n is None:
            n = len(images) + 1
            images.append({'n': n, 'source': source, 'url': url})
        return f'{match.group(1)}{match.group(2)}halo-image:{n}{match.group(2)}'

    return _IMG_SRC_RE.sub(repl, markup)


def html_to_text(markup):
    text = re.sub(r'(?i)<img\b[^>]*\bsrc=["\']halo-image:(\d+)["\'][^>]*>', r'[image \1]', markup or '')
    text = re.sub(r'(?i)<br\s*/?>|</p>|</div>', '\n', text)
    text = html.unescape(_TAG_RE.sub('', text)).replace('\xa0', ' ')
    return re.sub(r'\n{3,}', '\n\n', text).strip()


def normalize_attachment(raw):
    keep = ('id', 'filename', 'filesize', 'isimage', 'datecreated', 'desc', 'note', 'type')
    return _compact({k: raw.get(k) for k in keep})


def build_ticket(ticket, actions_payload, attachments_payload, statuses, *, base):
    """Assemble the `ticket` output plus the in-memory inline image list."""
    images = []
    ticket = _compact(dict(ticket))
    status_names = {s.get('id'): s.get('name') for s in statuses or [] if isinstance(s, dict)}
    ticket['status_name'] = status_names.get(ticket.get('status_id'))
    if 'details_html' in ticket:
        ticket['details_html'] = extract_images(ticket['details_html'], images, 'ticket')
    actions = []
    for raw in (actions_payload or {}).get('actions') or []:
        action = _compact(dict(raw))
        if 'note_html' in action:
            action['note_html'] = extract_images(action['note_html'], images, f'action:{action.get("id")}')
        actions.append(action)
    attachments = [normalize_attachment(a) for a in (attachments_payload or {}).get('attachments') or []]
    ticket_id = ticket.get('id')
    out = {
        'id': ticket_id,
        'url': f'{base}/ticket?id={ticket_id}',
        'summary': ticket.get('summary'),
        'status': {'id': ticket.get('status_id'), 'name': ticket.get('status_name')},
        'ticket': ticket,
        'actions': actions,
        'attachments': attachments,
        'images': [{k: v for k, v in img.items() if k != 'url'} for img in images],
    }
    return out, images


def format_ticket(out):
    t = out['ticket']
    lines = [
        f"#{out['id']} {out.get('summary') or ''}",
        f"status: {out['status'].get('name') or out['status'].get('id')}",
    ]
    for label, key in (('user', 'user_name'), ('team', 'team'), ('agent', 'agent_id'),
                       ('created', 'datecreated'), ('updated', 'last_update')):
        if t.get(key) not in (None, ''):
            lines.append(f'{label}: {t[key]}')
    lines.append(out['url'])
    details = html_to_text(t.get('details_html')) or t.get('details') or ''
    if details:
        lines += ['', details]
    for action in reversed(out['actions']):  # Halo lists newest first
        who = action.get('who') or '?'
        status = f" -> {action['new_status_name']}" if action.get('new_status_name') else ''
        lines += ['', f"--- {action.get('datetime', '')} {who}{status}"]
        note = html_to_text(action.get('note_html')) or action.get('note') or ''
        if note:
            lines.append(note)
    if out['attachments'] or out['images']:
        lines += ['', f"attachments: {len(out['attachments'])}, inline images: {len(out['images'])}"]
    return '\n'.join(lines)
