"""``owa-graph calendar`` - events.

Shortcuts:
    events     GET /me/events (or /me/calendarView with --from/--to)
    create     POST /me/events
    update     PATCH /me/events/{id}
    delete     DELETE /me/events/{id}
    findtimes  POST /me/findMeetingTimes
    accept     POST /me/events/{id}/accept
    decline    POST /me/events/{id}/decline
"""
from __future__ import annotations

from owa_core.errors import UsageError

from . import _argv


def cmd_events(args, ctx):
    parsed, _ = _argv.parse(args, flags=('--top', '--from', '--to', '--select'))
    if parsed.get('--from') and parsed.get('--to'):
        query = [('startDateTime', parsed['--from']),
                 ('endDateTime', parsed['--to']),
                 ('$top', parsed.get('--top', '25'))]
        if parsed.get('--select'):
            query.append(('$select', parsed['--select']))
        return ctx.get('/me/calendarView', query=query)
    query = [('$top', parsed.get('--top', '25')),
             ('$orderby', 'start/dateTime')]
    if parsed.get('--select'):
        query.append(('$select', parsed['--select']))
    return ctx.get('/me/events', query=query)


def cmd_create(args, ctx):
    parsed, _ = _argv.parse(
        args,
        flags=('--subject', '--start', '--end', '--attendees', '--body', '--tz'))
    if not all(parsed.get(k) for k in ('--subject', '--start', '--end')):
        raise UsageError('create requires --subject, --start, --end')
    tz = parsed.get('--tz', 'UTC')
    body = {
        'subject': parsed['--subject'],
        'start': {'dateTime': parsed['--start'], 'timeZone': tz},
        'end': {'dateTime': parsed['--end'], 'timeZone': tz},
    }
    if parsed.get('--body'):
        body['body'] = {'contentType': 'Text', 'content': parsed['--body']}
    if parsed.get('--attendees'):
        body['attendees'] = [
            {'emailAddress': {'address': a.strip()}, 'type': 'required'}
            for a in parsed['--attendees'].split(',') if a.strip()
        ]
    return ctx.post('/me/events', body)


def cmd_update(args, ctx):
    parsed, pos = _argv.parse(args, flags=('--id', '--subject', '--body'))
    ev_id = parsed.get('--id') or (pos[0] if pos else None)
    if not ev_id:
        raise UsageError('update requires --id')
    patch = {}
    if parsed.get('--subject'):
        patch['subject'] = parsed['--subject']
    if parsed.get('--body'):
        patch['body'] = {'contentType': 'Text', 'content': parsed['--body']}
    if not patch:
        raise UsageError('update needs at least one of --subject, --body')
    return ctx.patch(f'/me/events/{ev_id}', patch)


def cmd_delete(args, ctx):
    parsed, pos = _argv.parse(args, flags=('--id',))
    ev_id = parsed.get('--id') or (pos[0] if pos else None)
    if not ev_id:
        raise UsageError('delete requires --id')
    return ctx.delete(f'/me/events/{ev_id}')


def cmd_findtimes(args, ctx):
    parsed, _ = _argv.parse(args, flags=('--attendees', '--duration'))
    if not parsed.get('--attendees'):
        raise UsageError('findtimes requires --attendees a@x.com,b@x.com')
    body = {
        'attendees': [
            {'emailAddress': {'address': a.strip()}, 'type': 'required'}
            for a in parsed['--attendees'].split(',') if a.strip()
        ],
        'meetingDuration': parsed.get('--duration', 'PT30M'),
    }
    return ctx.post('/me/findMeetingTimes', body)


def _rsvp(args, ctx, action):
    parsed, pos = _argv.parse(args, flags=('--id', '--comment'))
    ev_id = parsed.get('--id') or (pos[0] if pos else None)
    if not ev_id:
        raise UsageError(f'{action} requires --id')
    return ctx.post(f'/me/events/{ev_id}/{action}',
                    {'comment': parsed.get('--comment', ''),
                     'sendResponse': True})


def cmd_accept(args, ctx):
    return _rsvp(args, ctx, 'accept')


def cmd_decline(args, ctx):
    return _rsvp(args, ctx, 'decline')


COMMANDS = {
    'events': (cmd_events, 'List events (or calendarView with --from/--to)'),
    'create': (cmd_create, 'Create event (--subject, --start, --end, [--attendees], [--body], [--tz])'),
    'update': (cmd_update, 'Update --id event (--subject, --body)'),
    'delete': (cmd_delete, 'Delete --id event'),
    'findtimes': (cmd_findtimes, 'Find meeting times (--attendees [--duration])'),
    'accept': (cmd_accept, 'Accept --id [--comment]'),
    'decline': (cmd_decline, 'Decline --id [--comment]'),
}
