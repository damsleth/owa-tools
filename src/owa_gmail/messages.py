"""Message shaping for Gmail's payload/parts tree. Pure functions, no I/O.

Gmail returns headers as a flat name/value list and body content as a
recursive multipart tree with base64url-encoded leaves (real mail nests
`multipart/alternative` inside `multipart/related` or `multipart/mixed`).
Attachment bytes are never inlined: a leaf with a `filename` carries only
`body.attachmentId` and `body.size`.
"""
import base64


def b64url_decode(data):
    """Gmail's `data`/`raw` fields are base64url, often without padding."""
    if not data:
        return b''
    return base64.urlsafe_b64decode(data + '=' * (-len(data) % 4))


def header(headers, name):
    """Case-insensitive lookup in Gmail's [{"name","value"}] header list."""
    target = name.lower()
    for h in headers or []:
        if (h.get('name') or '').lower() == target:
            return h.get('value') or ''
    return ''


def walk_parts(payload):
    """Every leaf part, depth-first. A non-multipart message is its own leaf."""
    parts = payload.get('parts')
    if not parts:
        yield payload
        return
    for part in parts:
        yield from walk_parts(part)


def extract_bodies(payload):
    """(plain, html): the first text/plain and text/html leaves, decoded.
    Attachment leaves (with a filename) are skipped even if text-typed."""
    plain, html = '', ''
    for part in walk_parts(payload):
        data = (part.get('body') or {}).get('data')
        if not data or part.get('filename'):
            continue
        mime = part.get('mimeType') or ''
        if mime == 'text/plain' and not plain:
            plain = b64url_decode(data).decode('utf-8', errors='replace')
        elif mime == 'text/html' and not html:
            html = b64url_decode(data).decode('utf-8', errors='replace')
    return plain, html


def extract_attachments(payload):
    """[{filename, mime_type, attachment_id, size}] - metadata only."""
    out = []
    for part in walk_parts(payload):
        body = part.get('body') or {}
        if part.get('filename') and body.get('attachmentId'):
            out.append({
                'filename': part['filename'],
                'mime_type': part.get('mimeType') or '',
                'attachment_id': body['attachmentId'],
                'size': body.get('size'),
            })
    return out


def normalize_message(raw, *, with_body=False):
    """Flatten a Gmail message resource to a stable snake_case shape."""
    payload = raw.get('payload') or {}
    headers = payload.get('headers') or []
    out = {
        'id': raw.get('id') or '',
        'thread_id': raw.get('threadId') or '',
        'label_ids': raw.get('labelIds') or [],
        'snippet': raw.get('snippet') or '',
        'internal_date_ms': int(raw.get('internalDate') or 0),
        'subject': header(headers, 'Subject'),
        'from': header(headers, 'From'),
        'to': header(headers, 'To'),
        'cc': header(headers, 'Cc'),
        'date': header(headers, 'Date'),
        'message_id': header(headers, 'Message-ID'),
    }
    if with_body:
        plain, html = extract_bodies(payload)
        out['body_plain'] = plain
        out['body_html'] = html
        out['attachments'] = extract_attachments(payload)
    return out


def build_list_query(*, sender='', to='', subject='', label='', unread=False,
                     has_attachment=False, since='', until='', search='',
                     max_results=25, page_token=''):
    """Gmail messages.list params. `q` is one search-operator string
    (space-joined terms are AND'd); `search` replaces the built query."""
    if search:
        q = search
    else:
        clauses = []
        if sender:
            clauses.append(f'from:{sender}')
        if to:
            clauses.append(f'to:{to}')
        if subject:
            clauses.append(f'subject:"{subject}"')
        if label:
            clauses.append(f'label:{label}')
        if unread:
            clauses.append('is:unread')
        if has_attachment:
            clauses.append('has:attachment')
        if since:
            clauses.append(f'after:{since.replace("-", "/")}')
        if until:
            clauses.append(f'before:{until.replace("-", "/")}')
        q = ' '.join(clauses)
    params = {'maxResults': max_results}
    if q:
        params['q'] = q
    if page_token:
        params['pageToken'] = page_token
    return params


def normalize_label(raw):
    return {'id': raw.get('id') or '', 'name': raw.get('name') or '', 'type': raw.get('type') or ''}
