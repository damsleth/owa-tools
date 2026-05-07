"""``owa-graph groups`` - Microsoft 365 groups."""
from __future__ import annotations

from . import _argv


def cmd_list(args, ctx):
    parsed, _ = _argv.parse(args, flags=('--top', '--filter'))
    query = [('$top', parsed.get('--top', '25'))]
    if parsed.get('--filter'):
        query.append(('$filter', parsed['--filter']))
    return ctx.get('/groups', query=query)


def cmd_members(args, ctx):
    parsed, pos = _argv.parse(args, flags=('--id',))
    gid = parsed.get('--id') or (pos[0] if pos else None)
    if not gid:
        print('ERROR: members requires --id'); return 1
    return ctx.get(f'/groups/{gid}/members')


def cmd_add(args, ctx):
    parsed, _ = _argv.parse(args, flags=('--id', '--user'))
    if not parsed.get('--id') or not parsed.get('--user'):
        print('ERROR: add requires --id <group> --user <user-id>'); return 1
    base = ctx.api_base.rstrip('/')
    body = {'@odata.id': f"{base}/directoryObjects/{parsed['--user']}"}
    return ctx.post(f"/groups/{parsed['--id']}/members/$ref", body)


def cmd_remove(args, ctx):
    parsed, _ = _argv.parse(args, flags=('--id', '--user'))
    if not parsed.get('--id') or not parsed.get('--user'):
        print('ERROR: remove requires --id <group> --user <user-id>'); return 1
    return ctx.delete(
        f"/groups/{parsed['--id']}/members/{parsed['--user']}/$ref")


COMMANDS = {
    'list': (cmd_list, 'List groups'),
    'members': (cmd_members, 'List group members (--id)'),
    'add': (cmd_add, 'Add member (--id --user)'),
    'remove': (cmd_remove, 'Remove member (--id --user)'),
}
