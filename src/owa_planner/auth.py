"""Token acquisition. Audience: graph.

The OWA SPA client owa-piggy borrows carries Group.ReadWrite.All on the
Graph audience, which authorizes the Microsoft Graph `/planner` reads
owa-planner makes - even though the token carries no Tasks.* scope. Planner
reads are gated on Group.*, verified live 2026-06-01: `GET /me/planner/plans`
and `GET /groups/{id}/planner/plans` both return 200 on this token.

Thin wrapper over owa_core.auth - see owa_people/auth.py for the same shape.
"""

from owa_core import auth as _core
from owa_core.errors import OwaError, emit_error

TOOL_NAME = 'owa-planner'
AUDIENCE = 'graph'
API_BASE = 'https://graph.microsoft.com/v1.0'


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
