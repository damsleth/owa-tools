"""``owa-graph presence`` - Teams presence."""
from __future__ import annotations

from . import _argv


def cmd_me(args, ctx):
    _argv.parse(args)
    return ctx.get('/me/presence')


def cmd_get(args, ctx):
    parsed, pos = _argv.parse(args, flags=('--id',))
    user_id = parsed.get('--id') or (pos[0] if pos else None)
    if not user_id:
        print('ERROR: get requires a user id'); return 1
    return ctx.get(f'/users/{user_id}/presence')


def cmd_set(args, ctx):
    parsed, _ = _argv.parse(
        args, flags=('--availability', '--activity', '--duration', '--app'))
    if not parsed.get('--availability'):
        print('ERROR: set requires --availability (Available|Busy|DoNotDisturb|Away)')
        return 1
    body = {
        'sessionId': parsed.get('--app', '00000000-0000-0000-0000-000000000000'),
        'availability': parsed['--availability'],
        'activity': parsed.get('--activity', parsed['--availability']),
    }
    if parsed.get('--duration'):
        body['expirationDuration'] = parsed['--duration']
    return ctx.post('/me/presence/setPresence', body)


COMMANDS = {
    'me': (cmd_me, 'Show my presence'),
    'get': (cmd_get, "Show another user's presence (--id)"),
    'set': (cmd_set, 'Set my presence (--availability [--activity] [--duration PT1H])'),
}
