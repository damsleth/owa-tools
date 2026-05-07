"""Message JSON shaping.

Pure functions only. Outlook REST returns PascalCase with nested
`EmailAddress` objects; we flatten to a snake_case shape that's stable
for `--pretty`, JSON consumers and our own internal use. Build helpers
go the other way: from CLI flags to the Outlook payload shape.
"""
import urllib.parse

from . import scheduled as scheduled_mod

# Shared $select clauses. Listing skips Body (heavy); show fetches it.
LIST_SELECT = (
    'Id,ConversationId,ReceivedDateTime,Subject,From,ToRecipients,'
    'CcRecipients,BccRecipients,BodyPreview,IsRead,HasAttachments,'
    'Importance,Flag,WebLink,ParentFolderId'
)
SHOW_SELECT = (
    'Id,ConversationId,ReceivedDateTime,SentDateTime,Subject,From,'
    'ToRecipients,CcRecipients,BccRecipients,BodyPreview,Body,IsRead,'
    'HasAttachments,Importance,Flag,WebLink,ParentFolderId'
)


def message_path(message_id):
    """Build the REST path for a single message by id (id is URL-encoded)."""
    return f'me/messages/{urllib.parse.quote(message_id, safe="")}'


def build_list_query(unread=False, sender='', subject_q='', search='',
                     since='', until='', limit=25, select=None):
    """Build the OData params dict for a messages listing.

    Encodes two non-obvious Outlook REST quirks:

    - `$search` and `$filter` are mutually exclusive at the API level.
      Caller is responsible for input-side validation; this builder
      will silently prefer `$search` if both are passed.
    - `contains(...)` filters combined with `$orderby ReceivedDateTime`
      can return InefficientFilter (HTTP 400) on real mailboxes. We drop
      `$orderby` whenever a Subject/From contains-clause is present.
    """
    params = {'$top': limit, '$select': select or LIST_SELECT}
    if not sender and not subject_q:
        params['$orderby'] = 'ReceivedDateTime desc'
    if search:
        # Outlook REST wants the value double-quoted inside $search="...".
        params['$search'] = f'"{search}"'
        return params
    clauses = []
    if unread:
        clauses.append('IsRead eq false')
    if sender:
        esc = sender.replace("'", "''")
        clauses.append(f"contains(From/EmailAddress/Address,'{esc}')")
    if subject_q:
        esc = subject_q.replace("'", "''")
        clauses.append(f"contains(Subject,'{esc}')")
    if since:
        clauses.append(f"ReceivedDateTime ge {since}T00:00:00Z")
    if until:
        clauses.append(f"ReceivedDateTime le {until}T23:59:59Z")
    if clauses:
        params['$filter'] = ' and '.join(clauses)
    return params


def _pick_str(d, *keys):
    """First non-empty string among `keys` in dict `d`, or ''.

    Outlook REST is inconsistent: PascalCase on the v2.0 audience, camelCase
    on Graph. This helper collapses the `d.get('Foo') or d.get('foo') or ''`
    chain that scalar fields need.
    """
    if not isinstance(d, dict):
        return ''
    for k in keys:
        v = d.get(k)
        if v:
            return v
    return ''


def _pick_dict(d, *keys):
    """First dict-valued match among `keys` in `d`, or {}."""
    if not isinstance(d, dict):
        return {}
    for k in keys:
        v = d.get(k)
        if isinstance(v, dict):
            return v
    return {}


def _pick_list(d, *keys):
    """First list-valued match among `keys` in `d`, or []."""
    if not isinstance(d, dict):
        return []
    for k in keys:
        v = d.get(k)
        if isinstance(v, list):
            return v
    return []


def _addr(rec):
    """Pull a flat email address out of an EmailAddress wrapper.

    Outlook returns `{"EmailAddress": {"Address": "...", "Name": "..."}}`
    for sender / recipient slots; we surface just the address."""
    inner = _pick_dict(rec, 'EmailAddress', 'emailAddress')
    return _pick_str(inner, 'Address', 'address')


def _addrs(items):
    if not isinstance(items, list):
        return ''
    out = [_addr(x) for x in items]
    return ', '.join(a for a in out if a)


def _flag_status(flag):
    return _pick_str(flag, 'FlagStatus', 'flagStatus')


def normalize_message(raw):
    """Flatten one Outlook REST message to our snake_case shape.

    Body is omitted from list output (`messages` listing) but included
    on `show`. Callers requesting a single message pass `include_body=True`.
    """
    if not isinstance(raw, dict):
        return {}
    body = _pick_dict(raw, 'Body', 'body')
    return {
        'id': _pick_str(raw, 'Id', 'id'),
        'conversation_id': _pick_str(raw, 'ConversationId', 'conversationId'),
        'received': _pick_str(raw, 'ReceivedDateTime', 'receivedDateTime'),
        'sent': _pick_str(raw, 'SentDateTime', 'sentDateTime'),
        'subject': _pick_str(raw, 'Subject', 'subject'),
        'from': _addr(_pick_dict(raw, 'From', 'from')),
        'to': _addrs(_pick_list(raw, 'ToRecipients', 'toRecipients')),
        'cc': _addrs(_pick_list(raw, 'CcRecipients', 'ccRecipients')),
        'bcc': _addrs(_pick_list(raw, 'BccRecipients', 'bccRecipients')),
        'preview': _pick_str(raw, 'BodyPreview', 'bodyPreview'),
        'is_read': bool(raw.get('IsRead', raw.get('isRead', False))),
        'has_attachments': bool(raw.get('HasAttachments', raw.get('hasAttachments', False))),
        'importance': _pick_str(raw, 'Importance', 'importance'),
        'flag': _flag_status(_pick_dict(raw, 'Flag', 'flag')),
        'folder_id': _pick_str(raw, 'ParentFolderId', 'parentFolderId'),
        'web_link': _pick_str(raw, 'WebLink', 'webLink'),
        'body_type': _pick_str(body, 'ContentType', 'contentType'),
        'body': _pick_str(body, 'Content', 'content'),
    }


def normalize_messages(raw):
    items = raw.get('value', []) if isinstance(raw, dict) else []
    out = []
    for m in items:
        flat = normalize_message(m)
        # Drop body fields from list view to keep payloads tight.
        flat.pop('body', None)
        flat.pop('body_type', None)
        out.append(flat)
    return out


def _split_addrs(value):
    """Split a comma- or semicolon-separated address string into a list,
    dropping empties. Whitespace is trimmed."""
    if not value:
        return []
    parts = []
    for chunk in value.replace(';', ',').split(','):
        s = chunk.strip()
        if s:
            parts.append(s)
    return parts


def _to_recipient_array(addrs):
    return [{'EmailAddress': {'Address': a}} for a in addrs]


def _importance_value(value):
    """Normalise importance string to Outlook's casing. None / empty
    means "unset" - the caller drops the key entirely."""
    if not value:
        return None
    v = value.strip().lower()
    if v in ('low', 'normal', 'high'):
        return v.capitalize()
    raise ValueError(f'invalid importance: {value} (use low|normal|high)')


def build_message_body(to, cc, bcc, subject, body, html, importance=''):
    """Build the `Message` substructure shared by send / draft.

    Recipient inputs are comma/semicolon-separated strings; outputs are
    Outlook's nested-object arrays. body is treated as text by default;
    `html=True` switches ContentType to HTML so Outlook renders markup
    instead of escaping it.
    """
    if not subject:
        raise ValueError('--subject is required')
    to_list = _split_addrs(to)
    if not to_list:
        raise ValueError('--to is required (one or more addresses)')
    msg = {
        'Subject': subject,
        'Body': {
            'ContentType': 'HTML' if html else 'Text',
            'Content': body or '',
        },
        'ToRecipients': _to_recipient_array(to_list),
    }
    cc_list = _split_addrs(cc)
    if cc_list:
        msg['CcRecipients'] = _to_recipient_array(cc_list)
    bcc_list = _split_addrs(bcc)
    if bcc_list:
        msg['BccRecipients'] = _to_recipient_array(bcc_list)
    imp = _importance_value(importance)
    if imp:
        msg['Importance'] = imp
    return msg


def build_send_payload(message_body):
    """Wrap a Message body for the one-shot `/me/sendMail` endpoint."""
    return {'Message': message_body, 'SaveToSentItems': True}


def build_draft_payload(message_body, send_at=None):
    """Build the body for `POST /me/messages` (creates a Draft).

    If `send_at` is set we attach the PR_DEFERRED_SEND_TIME extended
    property so Exchange Transport holds the message in Outbox until
    the scheduled time.
    """
    payload = dict(message_body)
    if send_at:
        payload['SingleValueExtendedProperties'] = (
            scheduled_mod.build_deferred_send_props(send_at)
        )
    return payload


def build_reply_patch(body, html, send_at=None, extra_to=None):
    """Build the PATCH body used to fill in a createReply / createReplyAll
    / createForward draft before sending.

    `body=None` means "leave the draft body alone"; any other value
    becomes the Body content. `html` switches ContentType when a body is
    supplied. For forward, `extra_to` overrides the (empty)
    ToRecipients on the draft.
    """
    patch = {}
    if body is not None:
        patch['Body'] = {
            'ContentType': 'HTML' if html else 'Text',
            'Content': body or '',
        }
    if extra_to:
        patch['ToRecipients'] = _to_recipient_array(_split_addrs(extra_to))
    if send_at:
        patch['SingleValueExtendedProperties'] = (
            scheduled_mod.build_deferred_send_props(send_at)
        )
    return patch


def build_mark_patch(read=None, flag=None):
    """Build the PATCH body for `mark`. Caller passes booleans for
    read (True/False) and flag (True=Flagged, False=NotFlagged), or
    None to leave a field untouched.
    """
    patch = {}
    if read is not None:
        patch['IsRead'] = bool(read)
    if flag is not None:
        patch['Flag'] = {
            'FlagStatus': 'Flagged' if flag else 'NotFlagged'
        }
    return patch
