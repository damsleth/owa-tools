"""``owa-graph users`` - directory users."""
from __future__ import annotations

from . import _argv


def cmd_list(args, ctx):
    parsed, _ = _argv.parse(args, flags=('--top', '--select', '--filter'))
    query = [('$top', parsed.get('--top', '25'))]
    if parsed.get('--select'):
        query.append(('$select', parsed['--select']))
    if parsed.get('--filter'):
        query.append(('$filter', parsed['--filter']))
    return ctx.get('/users', query=query, pretty_shape='users')


def cmd_find(args, ctx):
    parsed, pos = _argv.parse(args, flags=('--q', '--top'))
    term = parsed.get('--q') or (pos[0] if pos else None)
    if not term:
        print('ERROR: find requires a search term'); return 1
    query = [('$search', f'"displayName:{term}" OR "mail:{term}"'),
             ('$top', parsed.get('--top', '10'))]
    headers = {'ConsistencyLevel': 'eventual'}
    return ctx.get('/users', query=query, headers=headers, pretty_shape='users')


def cmd_get(args, ctx):
    parsed, pos = _argv.parse(args, flags=('--id',))
    user_id = parsed.get('--id') or (pos[0] if pos else None)
    if not user_id:
        print('ERROR: get requires a user id (positional or --id)'); return 1
    return ctx.get(f'/users/{user_id}', pretty_shape='users')


def cmd_manager(args, ctx):
    parsed, pos = _argv.parse(args, flags=('--id',))
    user_id = parsed.get('--id') or (pos[0] if pos else None)
    if not user_id:
        print('ERROR: manager requires a user id'); return 1
    return ctx.get(f'/users/{user_id}/manager', pretty_shape='users')


def cmd_directreports(args, ctx):
    parsed, pos = _argv.parse(args, flags=('--id',))
    user_id = parsed.get('--id') or (pos[0] if pos else None)
    if not user_id:
        print('ERROR: directreports requires a user id'); return 1
    return ctx.get(f'/users/{user_id}/directReports', pretty_shape='users')


COMMANDS = {
    'list': (cmd_list, 'List users (--top, --select, --filter)'),
    'find': (cmd_find, 'Search users by displayName or mail'),
    'get': (cmd_get, 'Show one user by --id (or positional)'),
    'manager': (cmd_manager, "Show user's manager"),
    'directreports': (cmd_directreports, "List user's direct reports"),
}
