"""``owa-graph sites`` - SharePoint sites."""
from __future__ import annotations

from . import _argv


def cmd_find(args, ctx):
    parsed, pos = _argv.parse(args, flags=('--q',))
    term = parsed.get('--q') or (pos[0] if pos else None)
    if not term:
        print('ERROR: find requires a search term'); return 1
    return ctx.get('/sites', query=[('search', term)])


def cmd_lists(args, ctx):
    parsed, pos = _argv.parse(args, flags=('--site',))
    site = parsed.get('--site') or (pos[0] if pos else None)
    if not site:
        print('ERROR: lists requires --site <site-id>'); return 1
    return ctx.get(f'/sites/{site}/lists')


def cmd_items(args, ctx):
    parsed, pos = _argv.parse(args, flags=('--site', '--list', '--top'))
    site = parsed.get('--site') or (pos[0] if pos else None)
    lst = parsed.get('--list') or (pos[1] if len(pos) > 1 else None)
    if not site or not lst:
        print('ERROR: items requires --site and --list'); return 1
    query = [('$top', parsed.get('--top', '25')),
             ('$expand', 'fields')]
    return ctx.get(f'/sites/{site}/lists/{lst}/items', query=query)


COMMANDS = {
    'find': (cmd_find, 'Search SharePoint sites'),
    'lists': (cmd_lists, 'List lists on --site'),
    'items': (cmd_items, 'List items in --site --list'),
}
