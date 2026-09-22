"""Token acquisition. Audience: graph. /me/calendar/getSchedule needs
Calendars.Read.Shared on the Graph audience, which the OWA SPA scopes
do carry.

Thin wrapper over owa_core.auth - see owa_drive/auth.py for the
"""

from owa_core import auth as _core

TOOL_NAME = 'owa-sched'
AUDIENCE = 'graph'
API_BASE = 'https://graph.microsoft.com/v1.0'


def do_token_refresh(config, debug=False):
    return _core.refresh_access_token(
        config, tool_name=TOOL_NAME, audience=AUDIENCE, debug=debug,
    )


def setup_auth(config, debug=False):
    token = _core.get_token_for_config(
        config, tool_name=TOOL_NAME, audience=AUDIENCE, debug=debug,
    )
    return token.access_token, API_BASE
