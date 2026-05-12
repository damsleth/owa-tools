"""``owa-graph sites`` - SharePoint sites."""
from __future__ import annotations

from owa_core.errors import UsageError

from . import _argv


def cmd_find(args, ctx):
    parsed, pos = _argv.parse(args, flags=('--q',))
    term = parsed.get('--q') or (pos[0] if pos else None)
    if not term:
        raise UsageError('find requires a search term')
    return ctx.get('/sites', query=[('search', term)])


def cmd_lists(args, ctx):
    parsed, pos = _argv.parse(args, flags=('--site',))
    site = parsed.get('--site') or (pos[0] if pos else None)
    if not site:
        raise UsageError('lists requires --site <site-id>')
    return ctx.get(f'/sites/{site}/lists')


def cmd_items(args, ctx):
    parsed, pos = _argv.parse(args, flags=('--site', '--list', '--top'))
    site = parsed.get('--site') or (pos[0] if pos else None)
    lst = parsed.get('--list') or (pos[1] if len(pos) > 1 else None)
    if not site or not lst:
        raise UsageError('items requires --site and --list')
    query = [('$top', parsed.get('--top', '25')),
             ('$expand', 'fields')]
    return ctx.get(f'/sites/{site}/lists/{lst}/items', query=query)


COMMANDS = {
    'find': (cmd_find, 'Search SharePoint sites'),
    'lists': (cmd_lists, 'List lists on --site'),
    'items': (cmd_items, 'List items in --site --list'),
}
