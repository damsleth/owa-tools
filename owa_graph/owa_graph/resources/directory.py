"""``owa-graph directory`` - directory roles + audit logs (admin scope)."""
from __future__ import annotations

from . import _argv


def cmd_roles(args, ctx):
    _argv.parse(args)
    return ctx.get('/directoryRoles')


def cmd_auditlogs(args, ctx):
    parsed, _ = _argv.parse(args, flags=('--top', '--filter'))
    query = [('$top', parsed.get('--top', '25'))]
    if parsed.get('--filter'):
        query.append(('$filter', parsed['--filter']))
    return ctx.get('/auditLogs/directoryAudits', query=query)


COMMANDS = {
    'roles': (cmd_roles, 'List directory roles'),
    'auditlogs': (cmd_auditlogs, 'Recent directory audits (--top, --filter)'),
}
