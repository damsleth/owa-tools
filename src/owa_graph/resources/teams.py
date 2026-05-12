"""``owa-graph teams`` - joined teams + channels + channel messages."""
from __future__ import annotations

from owa_core.errors import UsageError

from . import _argv


def cmd_joined(args, ctx):
    _argv.parse(args)
    return ctx.get('/me/joinedTeams')


def cmd_channels(args, ctx):
    parsed, pos = _argv.parse(args, flags=('--team',))
    team = parsed.get('--team') or (pos[0] if pos else None)
    if not team:
        raise UsageError('channels requires --team <team-id>')
    return ctx.get(f'/teams/{team}/channels')


def cmd_messages(args, ctx):
    parsed, pos = _argv.parse(args, flags=('--team', '--channel', '--top'))
    team = parsed.get('--team') or (pos[0] if pos else None)
    channel = parsed.get('--channel') or (pos[1] if len(pos) > 1 else None)
    if not team or not channel:
        raise UsageError('messages requires --team and --channel')
    query = [('$top', parsed.get('--top', '20'))]
    return ctx.get(f'/teams/{team}/channels/{channel}/messages', query=query)


def cmd_send(args, ctx):
    parsed, _ = _argv.parse(args, flags=('--team', '--channel', '--body'))
    if not all(parsed.get(k) for k in ('--team', '--channel', '--body')):
        raise UsageError('send requires --team --channel --body')
    return ctx.post(
        f"/teams/{parsed['--team']}/channels/{parsed['--channel']}/messages",
        {'body': {'content': parsed['--body']}},
    )


def cmd_members(args, ctx):
    parsed, pos = _argv.parse(args, flags=('--team',))
    team = parsed.get('--team') or (pos[0] if pos else None)
    if not team:
        raise UsageError('members requires --team')
    return ctx.get(f'/teams/{team}/members')


COMMANDS = {
    'joined': (cmd_joined, 'List my joined teams'),
    'channels': (cmd_channels, 'List channels (--team <id>)'),
    'messages': (cmd_messages, 'List channel messages (--team --channel [--top])'),
    'send': (cmd_send, 'Post a channel message (--team --channel --body)'),
    'members': (cmd_members, 'List team members (--team <id>)'),
}
