"""Normalisation for /me/drive driveItem responses."""


def _is_folder(entry):
    return isinstance(entry.get('folder'), dict)


def _is_file(entry):
    return isinstance(entry.get('file'), dict)


def normalize_item(entry):
    """Project a Graph driveItem into a flat shape for owa-drive."""
    kind = 'folder' if _is_folder(entry) else ('file' if _is_file(entry) else 'unknown')
    out = {
        'id': entry.get('id') or '',
        'name': entry.get('name') or '',
        'kind': kind,
        'size': entry.get('size'),
        'lastModified': entry.get('lastModifiedDateTime') or '',
        'webUrl': entry.get('webUrl') or '',
        'parentPath': '',
        'mimeType': '',
        'childCount': None,
    }
    parent = entry.get('parentReference') or {}
    # `path` here looks like '/drive/root:/Documents'. Strip the prefix
    # so callers see a familiar tree path.
    raw = parent.get('path') or ''
    prefix = '/drive/root:'
    if raw.startswith(prefix):
        out['parentPath'] = raw[len(prefix):] or '/'
    if kind == 'file':
        f = entry.get('file') or {}
        out['mimeType'] = f.get('mimeType') or ''
    if kind == 'folder':
        folder = entry.get('folder') or {}
        out['childCount'] = folder.get('childCount')
    return out
