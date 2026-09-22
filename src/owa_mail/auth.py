"""Token acquisition. Audience: outlook (Outlook REST endpoint).

owa-mail targets `outlook.office.com`, matching owa-cal. The OWA SPA
client owa-piggy borrows carries Mail.ReadWrite on the Outlook
audience.

Thin wrapper over owa_core.auth - see owa_drive/auth.py for the
"""

from owa_core import auth as _core

TOOL_NAME = 'owa-mail'
AUDIENCE = 'outlook'
API_BASE = 'https://outlook.office.com/api/v2.0'


def do_token_refresh(config, debug=False):
    return _core.refresh_access_token(
        config, tool_name=TOOL_NAME, audience=AUDIENCE, debug=debug,
    )


def setup_auth(config, debug=False):
    token = _core.get_token_for_config(
        config, tool_name=TOOL_NAME, audience=AUDIENCE, debug=debug,
    )
    return token.access_token, API_BASE
