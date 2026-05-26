"""OneDrive path -> Graph endpoint translation.

Graph addresses items two ways:

    /me/drive/items/{id}                  - by id
    /me/drive/root:/path/to/file:/...     - by path

We only ever emit the path form. Pure functions; tests pin the
output exactly.
"""
import urllib.parse


def normalize_path(p):
    """Normalize a user-supplied path.

    - Empty / '/' / '.' -> '' (the root).
    - Leading slash stripped.
    - Trailing slash stripped (for stable equality, not correctness).
    - Inner whitespace preserved (filenames may contain spaces).
    """
    if p is None:
        return ''
    p = p.strip()
    if p in ('', '/', '.'):
        return ''
    p = p.lstrip('/').rstrip('/')
    return p


def _quote_segment(seg):
    # Graph wants segments URL-encoded but path separators preserved
    # in the surrounding ":/<path>:/" wrapper.
    return urllib.parse.quote(seg, safe='')


def _quoted_path(p):
    p = normalize_path(p)
    if not p:
        return ''
    return '/'.join(_quote_segment(s) for s in p.split('/'))


def item_endpoint(path):
    """Return the Graph endpoint for the item at `path`.

    Root: `me/drive/root`.
    Path: `me/drive/root:/foo/bar:`  (note trailing colon: caller
        appends `/children`, `/content`, or omits for the metadata
        endpoint via item_endpoint_meta).
    """
    qp = _quoted_path(path)
    if not qp:
        return 'me/drive/root'
    return f'me/drive/root:/{qp}:'


def children_endpoint(path):
    base = item_endpoint(path)
    if base == 'me/drive/root':
        return 'me/drive/root/children'
    return f'{base}/children'


def content_endpoint(path):
    """Endpoint for GET / PUT raw bytes."""
    base = item_endpoint(path)
    if base == 'me/drive/root':
        # The drive root cannot have content. Caller error.
        raise ValueError("the drive root has no content; specify a path")
    return f'{base}/content'


def upload_session_endpoint(path):
    """Endpoint for POST createUploadSession (large-file upload)."""
    base = item_endpoint(path)
    if base == 'me/drive/root':
        raise ValueError("the drive root has no content; specify a path")
    return f'{base}/createUploadSession'


def delete_endpoint(path):
    """Endpoint for DELETE.

    Graph's DELETE is on the metadata URL (no `:` at end).
    """
    qp = _quoted_path(path)
    if not qp:
        raise ValueError("refuse to delete the drive root")
    return f'me/drive/root:/{qp}'
