"""File shaping, the Drive `q` builder, and the Google-native export choice.
Pure functions, no I/O.

Google Docs/Sheets/Slides have no binary content: `alt=media` answers 403
"Only files with binary content can be downloaded", so `get` exports them
(`/files/{id}/export?mimeType=...`) to a text-friendly default instead.
"""

GOOGLE_NATIVE_PREFIX = 'application/vnd.google-apps.'
FOLDER_MIME = GOOGLE_NATIVE_PREFIX + 'folder'

# Text-friendly defaults (the ingestion use case wants readable text);
# override per call with --export-mime.
DEFAULT_EXPORT_MIME = {
    GOOGLE_NATIVE_PREFIX + 'document': 'text/plain',
    GOOGLE_NATIVE_PREFIX + 'spreadsheet': 'text/csv',
    GOOGLE_NATIVE_PREFIX + 'presentation': 'text/plain',
    GOOGLE_NATIVE_PREFIX + 'drawing': 'image/png',
}

LIST_FIELDS = 'nextPageToken,files(id,name,mimeType,size,modifiedTime,parents,webViewLink,trashed,owners(emailAddress))'
FILE_FIELDS = 'id,name,mimeType,size,modifiedTime,createdTime,parents,webViewLink,trashed,owners(emailAddress),description'


def is_google_native(mime_type):
    return (mime_type or '').startswith(GOOGLE_NATIVE_PREFIX)


def resolve_export_mime(mime_type, override=None):
    """Export target for a Google-native file, or None for a regular file
    (use alt=media). Raises ValueError for a native type with no default
    and no override (Forms, Sites, folders...)."""
    if not is_google_native(mime_type):
        return None
    if override:
        return override
    if mime_type in DEFAULT_EXPORT_MIME:
        return DEFAULT_EXPORT_MIME[mime_type]
    raise ValueError(f'{mime_type} cannot be downloaded; it has no default export format (try --export-mime)')


def normalize_file(entry):
    mime = entry.get('mimeType') or ''
    size = entry.get('size')
    out = {
        'id': entry.get('id') or '',
        'name': entry.get('name') or '',
        'kind': 'folder' if mime == FOLDER_MIME else 'file',
        'mime_type': mime,
        'is_google_native': is_google_native(mime),
        'size': int(size) if size is not None else None,
        'modified': entry.get('modifiedTime') or '',
        'parents': entry.get('parents') or [],
        'owners': [o.get('emailAddress') for o in entry.get('owners') or [] if o.get('emailAddress')],
        'web_view_link': entry.get('webViewLink') or '',
        'trashed': bool(entry.get('trashed')),
    }
    for key, src in (('created', 'createdTime'), ('description', 'description')):
        if entry.get(src):
            out[key] = entry[src]
    return out


def _escape(value):
    """Drive query string literals: backslash-escape `\\` and `'`
    (not OData's doubled quotes)."""
    return value.replace('\\', '\\\\').replace("'", "\\'")


def build_list_query(*, folder='', name='', search='', file_type='', shared=False, raw_query=''):
    """Drive `q` expression. `raw_query` replaces everything. Without a
    folder, name, search or `shared`, the caller passes folder='root' so a
    bare `ls` lists My Drive's top level, not every file in the Drive."""
    if raw_query:
        return raw_query
    clauses = ['trashed = false']
    if folder:
        clauses.append(f"'{_escape(folder)}' in parents")
    if shared:
        clauses.append('sharedWithMe')
    if name:
        clauses.append(f"name contains '{_escape(name)}'")
    if search:
        clauses.append(f"fullText contains '{_escape(search)}'")
    if file_type == 'folder':
        clauses.append(f"mimeType = '{FOLDER_MIME}'")
    elif file_type == 'file':
        clauses.append(f"mimeType != '{FOLDER_MIME}'")
    return ' and '.join(clauses)
