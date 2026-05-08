"""``owa-graph mail`` - messages.

Shortcuts:
    list      GET /me/mailFolders/{folder}/messages
    read      GET /me/messages/{id}
    send      POST /me/sendMail
    reply     POST /me/messages/{id}/reply
    replyall  POST /me/messages/{id}/replyAll
    forward   POST /me/messages/{id}/forward
    move      POST /me/messages/{id}/move
    flag      PATCH /me/messages/{id}  (followUp flag)
    delete    DELETE /me/messages/{id}
"""
from __future__ import annotations

from . import _argv

_LIST_FLAGS = ('--folder', '--top', '--select', '--filter')
_LIST_BOOLS = ('--unread',)


def cmd_list(args, ctx):
    parsed, _ = _argv.parse(args, flags=_LIST_FLAGS, bools=_LIST_BOOLS)
    folder = parsed.get('--folder', 'Inbox')
    query = []
    filters = []
    if parsed.get('--unread'):
        filters.append('isRead eq false')
    if parsed.get('--filter'):
        filters.append(parsed['--filter'])
    if filters:
        query.append(('$filter', ' and '.join(filters)))
    query.append(('$top', parsed.get('--top', '25')))
    if parsed.get('--select'):
        query.append(('$select', parsed['--select']))
    return ctx.get(f'/me/mailFolders/{folder}/messages',
                   query=query, pretty_shape='messages')


def cmd_read(args, ctx):
    parsed, pos = _argv.parse(args, flags=('--id',))
    msg_id = parsed.get('--id') or (pos[0] if pos else None)
    if not msg_id:
        print('ERROR: read requires --id <message-id>'); return 1
    return ctx.get(f'/me/messages/{msg_id}', pretty_shape='messages')


def _recipients(value):
    return [{'emailAddress': {'address': a.strip()}}
            for a in value.split(',') if a.strip()]


def cmd_send(args, ctx):
    parsed, _ = _argv.parse(args, flags=('--subject', '--to', '--cc', '--body'))
    if not parsed.get('--to') or not parsed.get('--subject'):
        print('ERROR: send requires --subject and --to'); return 1
    msg = {
        'subject': parsed['--subject'],
        'body': {'contentType': 'Text',
                 'content': parsed.get('--body', '')},
        'toRecipients': _recipients(parsed['--to']),
    }
    if parsed.get('--cc'):
        msg['ccRecipients'] = _recipients(parsed['--cc'])
    return ctx.post('/me/sendMail', {'message': msg, 'saveToSentItems': True})


def _reply_like(args, ctx, action):
    parsed, pos = _argv.parse(args, flags=('--id', '--comment'))
    msg_id = parsed.get('--id') or (pos[0] if pos else None)
    if not msg_id:
        print(f'ERROR: {action} requires --id <message-id>'); return 1
    body = {'comment': parsed.get('--comment', '')}
    return ctx.post(f'/me/messages/{msg_id}/{action}', body)


def cmd_reply(args, ctx):
    return _reply_like(args, ctx, 'reply')


def cmd_replyall(args, ctx):
    return _reply_like(args, ctx, 'replyAll')


def cmd_forward(args, ctx):
    parsed, pos = _argv.parse(args, flags=('--id', '--to', '--comment'))
    msg_id = parsed.get('--id') or (pos[0] if pos else None)
    if not msg_id or not parsed.get('--to'):
        print('ERROR: forward requires --id and --to'); return 1
    return ctx.post(f'/me/messages/{msg_id}/forward', {
        'comment': parsed.get('--comment', ''),
        'toRecipients': _recipients(parsed['--to']),
    })


def cmd_move(args, ctx):
    parsed, pos = _argv.parse(args, flags=('--id', '--to'))
    msg_id = parsed.get('--id') or (pos[0] if pos else None)
    dest = parsed.get('--to')
    if not msg_id or not dest:
        print('ERROR: move requires --id and --to <folder-id-or-name>'); return 1
    return ctx.post(f'/me/messages/{msg_id}/move', {'destinationId': dest})


def cmd_flag(args, ctx):
    parsed, pos = _argv.parse(args, flags=('--id', '--status'))
    msg_id = parsed.get('--id') or (pos[0] if pos else None)
    if not msg_id:
        print('ERROR: flag requires --id'); return 1
    status = parsed.get('--status', 'flagged')
    return ctx.patch(f'/me/messages/{msg_id}',
                     {'flag': {'flagStatus': status}})


def cmd_delete(args, ctx):
    parsed, pos = _argv.parse(args, flags=('--id',))
    msg_id = parsed.get('--id') or (pos[0] if pos else None)
    if not msg_id:
        print('ERROR: delete requires --id'); return 1
    return ctx.delete(f'/me/messages/{msg_id}')


COMMANDS = {
    'list': (cmd_list, 'List messages in a folder (default: Inbox; --unread, --top, --filter)'),
    'read': (cmd_read, 'Show a message by --id'),
    'send': (cmd_send, 'Send mail (--subject, --to, [--cc], [--body])'),
    'reply': (cmd_reply, 'Reply to --id [--comment]'),
    'replyall': (cmd_replyall, 'Reply-all to --id [--comment]'),
    'forward': (cmd_forward, 'Forward --id --to a,b [--comment]'),
    'move': (cmd_move, 'Move --id --to <folder-id-or-name>'),
    'flag': (cmd_flag, 'Flag --id [--status flagged|complete|notFlagged]'),
    'delete': (cmd_delete, 'Delete --id'),
}
