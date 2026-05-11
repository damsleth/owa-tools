"""``owa-graph chats`` - 1:1 and group chats."""
from __future__ import annotations

from . import _argv


def cmd_list(args, ctx):
    parsed, _ = _argv.parse(args, flags=('--top',))
    query = [('$top', parsed.get('--top', '20'))]
    return ctx.get('/me/chats', query=query)


def cmd_messages(args, ctx):
    parsed, pos = _argv.parse(args, flags=('--chat', '--top'))
    chat = parsed.get('--chat') or (pos[0] if pos else None)
    if not chat:
        print('ERROR: messages requires --chat <id>'); return 1
    query = [('$top', parsed.get('--top', '20'))]
    return ctx.get(f'/chats/{chat}/messages', query=query)


def cmd_send(args, ctx):
    parsed, _ = _argv.parse(args, flags=('--chat', '--body'))
    if not parsed.get('--chat') or not parsed.get('--body'):
        print('ERROR: send requires --chat --body'); return 1
    return ctx.post(f"/chats/{parsed['--chat']}/messages",
                    {'body': {'content': parsed['--body']}})


COMMANDS = {
    'list': (cmd_list, 'List my chats'),
    'messages': (cmd_messages, 'List chat messages (--chat <id>)'),
    'send': (cmd_send, 'Post chat message (--chat --body)'),
}
