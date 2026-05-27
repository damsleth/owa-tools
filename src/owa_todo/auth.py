"""Token acquisition. Audience: outlook (Outlook REST endpoint).

owa-todo targets `outlook.office.com`, not Microsoft Graph: the OWA SPA
client owa-piggy borrows does NOT carry Tasks.ReadWrite on the Graph
audience, but the `outlook` audience token does (To Do is served by
Outlook REST). See owa_cal/auth.py for the same reasoning on calendar.

Thin wrapper over owa_core.auth.
"""

from owa_core import auth as _core
from owa_core.errors import OwaError, emit_error

TOOL_NAME = 'owa-todo'
AUDIENCE = 'outlook'
API_BASE = 'https://outlook.office.com/api/v2.0'


def _refresh_via_owa_piggy(config, debug=False):
    try:
        token = _core.get_token_for_config(
            config, tool_name=TOOL_NAME, audience=AUDIENCE, debug=debug,
        )
    except OwaError as error:
        emit_error(error)
        return None
    return token.access_token


def do_token_refresh(config, debug=False):
    return _refresh_via_owa_piggy(config, debug=debug)


def setup_auth(config, debug=False):
    token = _core.get_token_for_config(
        config, tool_name=TOOL_NAME, audience=AUDIENCE, debug=debug,
    )
    return token.access_token, API_BASE
