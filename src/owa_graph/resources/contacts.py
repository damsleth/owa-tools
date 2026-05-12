"""``owa-graph contacts`` - personal contacts."""
from __future__ import annotations

from owa_core.errors import UsageError

from . import _argv


def cmd_list(args, ctx):
    parsed, _ = _argv.parse(args, flags=('--top',))
    query = [('$top', parsed.get('--top', '25'))]
    return ctx.get('/me/contacts', query=query)


def cmd_find(args, ctx):
    parsed, pos = _argv.parse(args, flags=('--q',))
    term = parsed.get('--q') or (pos[0] if pos else None)
    if not term:
        raise UsageError('find requires a search term')
    query = [('$search', f'"{term}"')]
    headers = {'ConsistencyLevel': 'eventual'}
    return ctx.get('/me/contacts', query=query, headers=headers)


def cmd_create(args, ctx):
    parsed, _ = _argv.parse(args, flags=('--name', '--email'))
    if not parsed.get('--name'):
        raise UsageError('create requires --name')
    body = {'displayName': parsed['--name']}
    if parsed.get('--email'):
        body['emailAddresses'] = [{'address': parsed['--email'],
                                   'name': parsed['--name']}]
    return ctx.post('/me/contacts', body)


def cmd_delete(args, ctx):
    parsed, pos = _argv.parse(args, flags=('--id',))
    cid = parsed.get('--id') or (pos[0] if pos else None)
    if not cid:
        raise UsageError('delete requires --id')
    return ctx.delete(f'/me/contacts/{cid}')


COMMANDS = {
    'list': (cmd_list, 'List my contacts'),
    'find': (cmd_find, 'Search contacts'),
    'create': (cmd_create, 'Create contact (--name [--email])'),
    'delete': (cmd_delete, 'Delete --id'),
}
