"""Attachment JSON shaping and payload building.

Pure functions only, mirroring messages.py. Outlook REST returns
attachments with `@odata.type` discriminators (`#Microsoft.OutlookServices.
FileAttachment` on the v2.0 audience, `#microsoft.graph.fileAttachment` on
Graph). We flatten to a stable snake_case shape for listing and build the
inline / upload-session payloads for sending.

Listing deliberately omits `ContentBytes` so we never dump base64 blobs
into terminal or JSON output. Downloads decode it (or read `$value`).
"""
import base64
import mimetypes
import os
import urllib.parse

# Fallback when the filename gives no hint; Graph/Outlook accept this and
# clients sniff the real type, but a specific type renders better (e.g.
# inline images, PDFs opening in-app).
_DEFAULT_CONTENT_TYPE = 'application/octet-stream'


def guess_content_type(name):
    """Best-effort MIME type from a filename, never None."""
    return mimetypes.guess_type(name)[0] or _DEFAULT_CONTENT_TYPE

# Files at or under this size are sent inline in the message; larger
# files go through a Graph upload session. Outlook's documented inline
# ceiling for a single POST/sendMail attachment is 3 MB.
INLINE_LIMIT_BYTES = 3 * 1024 * 1024

FILE_ATTACHMENT_TYPE = '#Microsoft.OutlookServices.FileAttachment'


def _pick_str(d, *keys):
    if not isinstance(d, dict):
        return ''
    for k in keys:
        v = d.get(k)
        if v:
            return v
    return ''


def _short_type(odata_type):
    """Reduce an `@odata.type` discriminator to a short label.

    `#Microsoft.OutlookServices.FileAttachment` -> `fileAttachment`,
    `#microsoft.graph.itemAttachment` -> `itemAttachment`.
    """
    if not odata_type:
        return ''
    tail = odata_type.rsplit('.', 1)[-1]
    return tail[:1].lower() + tail[1:] if tail else ''


def attachment_path(message_id, attachment_id=''):
    """Build the REST path to a message's attachments collection or item."""
    base = f'me/messages/{urllib.parse.quote(message_id, safe="")}/attachments'
    if attachment_id:
        return f'{base}/{urllib.parse.quote(attachment_id, safe="")}'
    return base


def value_path(message_id, attachment_id):
    """Build the `$value` raw-bytes path for one file attachment."""
    return f'{attachment_path(message_id, attachment_id)}/$value'


def createuploadsession_path(message_id):
    """Build the createUploadSession path for a (draft) message."""
    return f'{attachment_path(message_id)}/createUploadSession'


def normalize_attachment(raw):
    """Flatten one Outlook REST attachment to our snake_case shape.

    Surfaces id/name/type/size and the short attachment kind. Never
    includes `ContentBytes` - that is fetched separately on download.
    """
    if not isinstance(raw, dict):
        return {}
    odata = _pick_str(raw, '@odata.type', '@odata.Type')
    return {
        'id': _pick_str(raw, 'Id', 'id'),
        'name': _pick_str(raw, 'Name', 'name'),
        'content_type': _pick_str(raw, 'ContentType', 'contentType'),
        'size': int(raw.get('Size', raw.get('size', 0)) or 0),
        'kind': _short_type(odata),
        'is_inline': bool(raw.get('IsInline', raw.get('isInline', False))),
    }


def normalize_attachments(raw):
    items = raw.get('value', []) if isinstance(raw, dict) else []
    return [normalize_attachment(a) for a in items]


def decode_content_bytes(raw):
    """Decode a file attachment's base64 `ContentBytes` to raw bytes.

    Returns None when the field is absent (e.g. item/reference
    attachments, which have no inline bytes).
    """
    if not isinstance(raw, dict):
        return None
    b64 = _pick_str(raw, 'ContentBytes', 'contentBytes')
    if not b64:
        return None
    return base64.b64decode(b64)


def read_file_attachment(path):
    """Read a local file into an (name, content_bytes) pair.

    Raises ValueError with a CLI-friendly message on a missing or
    unreadable path so callers can surface it on stderr.
    """
    if not os.path.isfile(path):
        raise ValueError(f'attachment not found: {path}')
    try:
        with open(path, 'rb') as fh:
            return os.path.basename(path), fh.read()
    except OSError as exc:
        raise ValueError(f'cannot read attachment {path}: {exc}')


def build_inline_attachment(name, content_bytes, content_type=None):
    """Build one inline fileAttachment object for a message payload.

    `content_type` is guessed from the filename when not given so the
    attachment lands with a real MIME type instead of octet-stream.
    """
    return {
        '@odata.type': FILE_ATTACHMENT_TYPE,
        'Name': name,
        'ContentType': content_type or guess_content_type(name),
        'ContentBytes': base64.b64encode(content_bytes).decode('ascii'),
    }


def build_upload_session_body(name, size, content_type=None):
    """Build the createUploadSession request body for a large attachment.

    `content_type` is guessed from the filename when not given.
    """
    return {
        'AttachmentItem': {
            'attachmentType': 'file',
            'name': name,
            'size': size,
            'contentType': content_type or guess_content_type(name),
        }
    }


def partition_by_size(loaded, limit=INLINE_LIMIT_BYTES):
    """Split `[(name, bytes), ...]` into (small, large) by `limit`.

    `small` items can be inlined into the message/draft; `large` items
    must each go through an upload session.
    """
    small, large = [], []
    for name, content in loaded:
        if len(content) <= limit:
            small.append((name, content))
        else:
            large.append((name, content))
    return small, large
