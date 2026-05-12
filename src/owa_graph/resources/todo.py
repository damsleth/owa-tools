"""``owa-graph todo`` - Microsoft To-Do."""
from __future__ import annotations

from owa_core.errors import UsageError

from . import _argv


def cmd_lists(args, ctx):
    _argv.parse(args)
    return ctx.get('/me/todo/lists')


def cmd_tasks(args, ctx):
    parsed, pos = _argv.parse(args, flags=('--list', '--top'))
    lst = parsed.get('--list') or (pos[0] if pos else None)
    if not lst:
        raise UsageError('tasks requires --list <list-id>')
    query = [('$top', parsed.get('--top', '25'))]
    return ctx.get(f'/me/todo/lists/{lst}/tasks', query=query)


def cmd_add(args, ctx):
    parsed, _ = _argv.parse(args, flags=('--list', '--title', '--body'))
    if not parsed.get('--list') or not parsed.get('--title'):
        raise UsageError('add requires --list --title')
    body = {'title': parsed['--title']}
    if parsed.get('--body'):
        body['body'] = {'contentType': 'text', 'content': parsed['--body']}
    return ctx.post(f"/me/todo/lists/{parsed['--list']}/tasks", body)


def cmd_complete(args, ctx):
    parsed, _ = _argv.parse(args, flags=('--list', '--id'))
    if not parsed.get('--list') or not parsed.get('--id'):
        raise UsageError('complete requires --list --id')
    return ctx.patch(
        f"/me/todo/lists/{parsed['--list']}/tasks/{parsed['--id']}",
        {'status': 'completed'},
    )


COMMANDS = {
    'lists': (cmd_lists, 'List my todo lists'),
    'tasks': (cmd_tasks, 'List tasks in --list'),
    'add': (cmd_add, 'Add task (--list --title [--body])'),
    'complete': (cmd_complete, 'Mark task complete (--list --id)'),
}
