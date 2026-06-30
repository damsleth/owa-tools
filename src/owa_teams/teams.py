"""URL builders + response normalizers for owa-teams.

Two API shapes are normalized here to one stable lowercase wire shape:

  * **Graph** collections (`/me/joinedTeams`, `/teams/{id}/channels`,
    `/me/chats`) -> teams / channels / chats rows.
  * **chatsvc** message streams
    (`/users/ME/conversations/{id}/messages`) -> message rows.

Channel threading is the subtle part. The chatsvc channel stream is flat: it
returns root posts AND their replies interleaved, ordered by a monotonic
top-level `sequenceId`. The thread key is the top-level **`rootMessageId`**
(NOT `properties.parentmessageid`, which is null in practice). A message is a
ROOT when `rootMessageId` is absent / `"0"` / equal to its own `id`, and only
roots carry `properties.subject`. So one flat pass reconstructs every thread:
`thread_id = "{channel_id}:{root_id}"`, and a reply inherits its root's subject.
Verified live 2026-06-02. Chats, by contrast, are genuinely flat - one chat is
one thread.
"""
import datetime as _dt
import html as _html
import json
import re
import urllib.parse
import uuid

# --- HTML body stripping ------------------------------------------------------
# Teams message bodies are RichText/Html. Unwrap @-mentions to their text,
# drop attachment placeholders, strip remaining tags, unescape entities, and
# collapse runs of whitespace.
_MENTION_RE = re.compile(r'<at[^>]*>(.*?)</at>', re.IGNORECASE | re.DOTALL)
_ATTACHMENT_RE = re.compile(r'<attachment[^>]*>.*?</attachment>|<attachment[^>]*/?>', re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r'<[^>]+>')
_WS_RE = re.compile(r'[ \t]+')

# A chatsvc `from` is a URL like `.../contacts/8:orgid:<oid>`; `8:orgid:` is a
# tenant user, `28:`/`48:` are bots/apps. We pull the bare MRI out.
_FROM_MRI_RE = re.compile(r'/contacts/([0-9]+:[^/?#]+)')
# chatsvc may emit 7-digit fractional seconds; datetime.fromisoformat chokes
# pre-3.11, so downstream consumers trim - we just hand back the raw string.


def strip_html(text):
    if not text:
        return ''
    text = _MENTION_RE.sub(r'\1', text)
    text = _ATTACHMENT_RE.sub('', text)
    text = _TAG_RE.sub(' ', text)
    text = _html.unescape(text)
    lines = [_WS_RE.sub(' ', line).strip() for line in text.splitlines()]
    return '\n'.join(line for line in lines if line).strip()


def _q(value):
    return urllib.parse.quote(str(value), safe='')


# A trailing fractional-second run longer than microseconds (chatsvc emits 7
# digits) is what trips datetime.fromisoformat; trim it back to 6.
_OVERLONG_FRACTION_RE = re.compile(r'^(.*\.\d{6})\d+(.*)$')


def parse_iso(value):
    """Parse an ISO-8601 timestamp into an aware UTC datetime, or None.

    Tolerates a trailing ``Z`` and chatsvc's 7-digit fractional seconds (which
    ``datetime.fromisoformat`` rejects) by trimming the fraction to microseconds.
    A bare date (``2026-06-01``) parses as midnight UTC. Naive inputs are read as
    UTC. Returns ``None`` for empty/unparseable values so callers can decide.
    """
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith(('Z', 'z')):
        text = text[:-1] + '+00:00'
    match = _OVERLONG_FRACTION_RE.match(text)
    if match:
        text = match.group(1) + match.group(2)
    try:
        parsed = _dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_dt.timezone.utc)
    return parsed.astimezone(_dt.timezone.utc)


# --- Graph endpoint builders --------------------------------------------------

def joined_teams_endpoint():
    # Graph rejects $select/$top on /me/joinedTeams under delegated auth (400).
    return 'me/joinedTeams'


def channels_endpoint(team_id):
    select = 'id,displayName,description,membershipType,isArchived'
    return f'teams/{_q(team_id)}/channels?$select={select}'


def chats_endpoint(top=50):
    select = 'id,topic,chatType,lastUpdatedDateTime'
    return f'me/chats?$select={select}&$top={int(top)}'


def chat_members_endpoint(chat_id):
    return f'chats/{_q(chat_id)}/members'


def channel_members_endpoint(team_id, channel_id):
    # Reachable only with ChannelMember.Read.All, which owa-piggy's FOCI client
    # cannot obtain (live probe 2026-06-30: 403). Built for completeness; the
    # 403 surfaces as ScopeInsufficientError (exit 12) - see AGENTS.md.
    return f'teams/{_q(team_id)}/channels/{_q(channel_id)}/members'


# --- chatsvc endpoint builder -------------------------------------------------

CHATSVC_VIEW = 'msnp24Equivalent|supportsMessageProperties'


def conversation_messages_url(base, conversation_id, *, page_size=50, view=CHATSVC_VIEW):
    """Build the chatsvc messages URL for a channel or chat conversation.

    `base` already includes `/api/chatsvc/{region}/v1`. The conversation id is
    the Graph channel id (`19:...@thread.tacv2`) or chat id
    (`19:...@unq.gbl.spaces`) - both use this same endpoint verbatim.
    """
    cid = _q(conversation_id)
    return (
        f'{base}/users/ME/conversations/{cid}/messages'
        f'?pageSize={int(page_size)}&view={_q(view)}'
    )


def conversation_post_url(base, conversation_id):
    """Build the chatsvc POST URL for sending a message to a conversation.

    Same `/users/ME/conversations/{id}/messages` path as the read endpoint, but
    without the read query string. Verified live 2026-06-30 (crayon/emea): an
    `ic3` bearer POSTs here returning 201 + `{OriginalArrivalTime}` for chats,
    channels, and `48:notes` (note-to-self).
    """
    return f'{base}/users/ME/conversations/{_q(conversation_id)}/messages'


# --- chatsvc message-body builders --------------------------------------------

# The Teams web client wraps an @-mention in `<at id="N">Display</at>` and
# carries the structured roster in `properties.mentions` (a JSON *string* of
# Skype Mention objects). File/link cards ride in `properties.files` (also a
# JSON string). Verified live 2026-06-30 (both shapes 201).
_MENTION_TYPE = 'http://schema.skype.com/Mention'


def build_mention(item_id, mri, display_name):
    """One `properties.mentions` entry for `<at id="{item_id}">`."""
    return {
        '@type': _MENTION_TYPE,
        'itemid': int(item_id),
        'mri': mri,
        'displayName': display_name or '',
    }


def build_file_attachment(item_id, name, url):
    """One `properties.files` entry describing a link/file card."""
    return {
        '@type': 'http://schema.skype.com/File',
        'version': 2,
        'id': str(item_id),
        'baseUrl': url,
        'type': 'link',
        'title': name or url,
        'objectUrl': url,
        'fileName': name or url,
    }


def _mention_html(item_id, display_name):
    safe = _html.escape(display_name or '')
    return f'<at id="{int(item_id)}">{safe}</at>'


def build_message_body(content, *, html=False, mentions=None, attachments=None,
                       root_message_id='', subject=''):
    """Assemble a chatsvc message POST body.

    `content` is the message text. With `html=True` it is treated as a raw HTML
    body and passed through; otherwise plain text is HTML-escaped. Each
    `mentions` entry (built by `build_mention`) prepends an `<at>` tag to the
    body and is serialized into `properties.mentions`. `attachments` (built by
    `build_file_attachment`) go into `properties.files`. A non-empty
    `root_message_id` threads the post as a reply to that root (channels);
    `subject` sets a new channel thread's subject.
    """
    mentions = list(mentions or [])
    attachments = list(attachments or [])
    body_html = content if html else _html.escape(content or '')
    if mentions:
        tags = ' '.join(_mention_html(m['itemid'], m['displayName']) for m in mentions)
        body_html = f'{tags} {body_html}'.strip()
    body = {
        'content': body_html,
        'messagetype': 'RichText/Html',
        'contenttype': 'text',
        'clientmessageid': _client_message_id(),
    }
    properties = {}
    if mentions:
        properties['mentions'] = json.dumps(mentions)
    if attachments:
        properties['files'] = json.dumps(attachments)
    if root_message_id:
        properties['rootMessageId'] = str(root_message_id)
    if subject:
        properties['subject'] = subject
    if properties:
        body['properties'] = properties
    return body


def _client_message_id():
    """A stable per-call idempotency key (chatsvc dedups on clientmessageid)."""
    return str(uuid.uuid4().int >> 64)


# --- Graph normalizers --------------------------------------------------------

def _values(payload):
    if isinstance(payload, dict) and isinstance(payload.get('value'), list):
        return payload['value']
    if isinstance(payload, list):
        return payload
    return []


def normalize_team(team):
    return {
        'id': team.get('id'),
        'displayName': team.get('displayName'),
        'description': team.get('description'),
        'isArchived': bool(team.get('isArchived')),
    }


def normalize_teams(payload):
    return [normalize_team(t) for t in _values(payload) if t.get('id')]


def normalize_channel(channel):
    return {
        'id': channel.get('id'),
        'displayName': channel.get('displayName'),
        'membershipType': channel.get('membershipType'),
        'description': channel.get('description'),
        'isArchived': bool(channel.get('isArchived')),
    }


def normalize_channels(payload):
    return [normalize_channel(c) for c in _values(payload) if c.get('id')]


def normalize_chat(chat):
    return {
        'id': chat.get('id'),
        'topic': chat.get('topic'),
        'chatType': chat.get('chatType'),
        'lastUpdated': chat.get('lastUpdatedDateTime'),
    }


def normalize_chats(payload, chat_type=''):
    rows = [normalize_chat(c) for c in _values(payload) if c.get('id')]
    if chat_type:
        rows = [r for r in rows if (r.get('chatType') or '') == chat_type]
    return rows


# --- chatsvc message normalizers ----------------------------------------------

def _sender(message):
    raw = message.get('from') or ''
    match = _FROM_MRI_RE.search(raw)
    mri = match.group(1) if match else (raw or '')
    user_id = mri[len('8:orgid:'):] if mri.startswith('8:orgid:') else mri
    return {
        'id': user_id,
        'name': (message.get('imdisplayname') or '').strip(),
        'mri': mri,
    }


def _timestamp(message):
    return message.get('originalarrivaltime') or message.get('composetime') or ''


def message_datetime(message):
    """The message's arrival time as an aware UTC datetime, or None if absent."""
    return parse_iso(_timestamp(message))


def is_system_message(message):
    mtype = (message.get('messagetype') or '').lower()
    return bool(mtype) and not (mtype.startswith('text') or mtype.startswith('richtext'))


def _root_id(message):
    """Return (root_id, is_reply) using the top-level rootMessageId key."""
    mid = str(message.get('id') or '')
    rid = str(message.get('rootMessageId') or '').strip()
    is_reply = bool(rid) and rid not in ('', '0', mid)
    return (rid if is_reply else mid), is_reply


def _channel_subjects(raw_messages):
    """Map root message id -> subject (only roots carry properties.subject)."""
    subjects = {}
    for message in raw_messages:
        root_id, is_reply = _root_id(message)
        if is_reply:
            continue
        subject = ((message.get('properties') or {}).get('subject') or '').strip()
        if subject:
            subjects[root_id] = subject
    return subjects


def normalize_channel_messages(raw_messages, *, team_id='', channel_id='', include_system=False):
    """Thread a flat chatsvc channel stream into chronological message rows.

    Input is newest-first (as chatsvc returns it); output is oldest-first.
    System events and empty bodies are dropped unless `include_system`.
    """
    subjects = _channel_subjects(raw_messages)
    rows = []
    for message in raw_messages:
        if is_system_message(message) and not include_system:
            continue
        content = strip_html(message.get('content') or '')
        if not content and not include_system:
            continue
        root_id, is_reply = _root_id(message)
        rows.append({
            'id': str(message.get('id') or ''),
            'threadId': f'{channel_id}:{root_id}' if channel_id else root_id,
            'rootMessageId': root_id,
            'isReply': is_reply,
            'sequenceId': message.get('sequenceId'),
            'from': _sender(message),
            'timestamp': _timestamp(message),
            'subject': subjects.get(root_id, ''),
            'content': content,
            'messageType': message.get('messagetype'),
            'teamId': team_id,
            'channelId': channel_id,
        })
    rows.reverse()
    return rows


def normalize_chat_messages(raw_messages, *, chat_id='', include_system=False):
    """Normalize a flat chatsvc chat stream into chronological message rows.

    Chats have no root/reply structure: one chat is one thread.
    """
    rows = []
    for message in raw_messages:
        if is_system_message(message) and not include_system:
            continue
        content = strip_html(message.get('content') or '')
        if not content and not include_system:
            continue
        rows.append({
            'id': str(message.get('id') or ''),
            'threadId': chat_id,
            'from': _sender(message),
            'timestamp': _timestamp(message),
            'content': content,
            'messageType': message.get('messagetype'),
            'chatId': chat_id,
        })
    rows.reverse()
    return rows


# --- members + send normalizers -----------------------------------------------

def normalize_member(member):
    """A Graph conversationMember -> a stable lowercase row."""
    return {
        'id': member.get('id'),
        'displayName': member.get('displayName'),
        'email': member.get('email'),
        'userId': member.get('userId'),
        'roles': member.get('roles') or [],
    }


def normalize_members(payload):
    return [normalize_member(m) for m in _values(payload)]


def normalize_send_result(conversation_id, body, payload):
    """Flatten a chatsvc POST response into a stable send-result row.

    The POST returns `{OriginalArrivalTime: <epoch-ms>}`; we echo the
    idempotency key and conversation so a consumer can correlate the send.
    """
    payload = payload if isinstance(payload, dict) else {}
    return {
        'sent': True,
        'conversationId': conversation_id,
        'clientMessageId': body.get('clientmessageid'),
        'originalArrivalTime': payload.get('OriginalArrivalTime'),
    }
