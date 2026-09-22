"""Token acquisition. Audience: graph. The OWA SPA client carries
People.Read, Contacts.Read, and User.ReadBasic.All on the Graph
audience, which is what every endpoint owa-people calls actually
needs.

Thin wrapper over owa_core.auth - see owa_drive/auth.py for the
"""

from owa_core import auth as _core

TOOL_NAME = 'owa-people'
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
