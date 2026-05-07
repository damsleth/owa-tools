"""``owa-graph files`` - OneDrive items.

Shortcuts:
    list      GET /me/drive/root/children (or by --path)
    download  GET /me/drive/items/{id}/content
    upload    PUT  /me/drive/root:/path:/content (small file)
    share     POST /me/drive/items/{id}/createLink
    delete    DELETE /me/drive/items/{id}
    search    GET /me/drive/root/search(q='term')
"""
from __future__ import annotations

import os
import sys

from . import _argv
from .. import api as api_mod


def cmd_list(args, ctx):
    parsed, _ = _argv.parse(args, flags=('--path', '--top'))
    if parsed.get('--path'):
        path = f"/me/drive/root:/{parsed['--path'].lstrip('/')}:/children"
    else:
        path = '/me/drive/root/children'
    query = [('$top', parsed.get('--top', '25'))]
    return ctx.get(path, query=query, pretty_shape='drive')


def cmd_download(args, ctx):
    parsed, pos = _argv.parse(args, flags=('--id', '--path'))
    if parsed.get('--id'):
        endpoint = f"/me/drive/items/{parsed['--id']}/content"
    elif parsed.get('--path') or pos:
        target = parsed.get('--path') or pos[0]
        endpoint = f"/me/drive/root:/{target.lstrip('/')}:/content"
    else:
        print('ERROR: download requires --id or --path'); return 1
    url = api_mod.build_url(ctx.api_base, endpoint)
    blob = api_mod.api_request(
        'GET', '', url, ctx.access_token,
        debug=ctx.debug, raw=True, retry=ctx.retry,
    )
    if blob is None:
        return 1
    sys.stdout.buffer.write(blob)
    return 0


def cmd_upload(args, ctx):
    parsed, pos = _argv.parse(args, flags=('--file', '--path'))
    src = parsed.get('--file') or (pos[0] if pos else None)
    dst = parsed.get('--path')
    if not src or not dst:
        print('ERROR: upload requires --file <local> --path <remote>'); return 1
    if not os.path.isfile(src):
        print(f'ERROR: not a file: {src}'); return 1
    with open(src, 'rb') as f:
        data = f.read()
    endpoint = f"/me/drive/root:/{dst.lstrip('/')}:/content"
    return ctx.put(endpoint, data, headers={'Content-Type': 'application/octet-stream'})


def cmd_share(args, ctx):
    parsed, pos = _argv.parse(args, flags=('--id', '--type', '--scope'))
    item_id = parsed.get('--id') or (pos[0] if pos else None)
    if not item_id:
        print('ERROR: share requires --id'); return 1
    body = {
        'type': parsed.get('--type', 'view'),
        'scope': parsed.get('--scope', 'organization'),
    }
    return ctx.post(f'/me/drive/items/{item_id}/createLink', body)


def cmd_delete(args, ctx):
    parsed, pos = _argv.parse(args, flags=('--id',))
    item_id = parsed.get('--id') or (pos[0] if pos else None)
    if not item_id:
        print('ERROR: delete requires --id'); return 1
    return ctx.delete(f'/me/drive/items/{item_id}')


def cmd_search(args, ctx):
    parsed, pos = _argv.parse(args, flags=('--q', '--top'))
    term = parsed.get('--q') or (pos[0] if pos else None)
    if not term:
        print('ERROR: search requires a query (positional or --q)'); return 1
    endpoint = f"/me/drive/root/search(q='{term}')"
    query = [('$top', parsed.get('--top', '25'))]
    return ctx.get(endpoint, query=query, pretty_shape='drive')


COMMANDS = {
    'list': (cmd_list, 'List drive items (root or --path; --top)'),
    'download': (cmd_download, 'Download to stdout (--id or --path)'),
    'upload': (cmd_upload, 'Upload --file to --path (small files only)'),
    'share': (cmd_share, 'Create share link (--id [--type view|edit] [--scope anonymous|organization])'),
    'delete': (cmd_delete, 'Delete --id'),
    'search': (cmd_search, 'Search drive (--q term [--top])'),
}
