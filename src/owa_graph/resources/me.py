"""``owa-graph me`` - profile + org graph.

Shortcuts:
    whoami         GET /me
    photo          GET /me/photo/$value (binary)
    manager        GET /me/manager
    directreports  GET /me/directReports
"""
from __future__ import annotations

from . import _argv


def cmd_whoami(args, ctx):
    _argv.parse(args)
    return ctx.get('/me', pretty_shape='me')


def cmd_photo(args, ctx):
    """Print the user's photo bytes to stdout (pipe into a file).

    ``$value`` returns binary; we go through ``api_request(raw=True)``
    via a direct call because the context emit path only does JSON.
    """
    import sys

    from .. import api as api_mod
    _argv.parse(args)
    url = api_mod.build_url(ctx.api_base, '/me/photo/$value')
    blob = api_mod.api_request(
        'GET', '', url, ctx.access_token,
        debug=ctx.debug, raw=True, retry=ctx.retry,
    )
    if blob is None:
        return 1
    sys.stdout.buffer.write(blob)
    return 0


def cmd_manager(args, ctx):
    _argv.parse(args)
    return ctx.get('/me/manager', pretty_shape='users')


def cmd_directreports(args, ctx):
    _argv.parse(args)
    return ctx.get('/me/directReports', pretty_shape='users')


COMMANDS = {
    'whoami': (cmd_whoami, 'Show the signed-in user (GET /me)'),
    'photo': (cmd_photo, "Print the signed-in user's photo bytes to stdout"),
    'manager': (cmd_manager, 'Show the signed-in user manager'),
    'directreports': (cmd_directreports, 'List direct reports'),
}
