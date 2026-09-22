"""Token acquisition. Audience: graph. The OWA SPA scopes carry
Files.ReadWrite.All, which covers /me/drive read + write.
"""
from owa_core import auth as _core

TOOL_NAME = 'owa-drive'
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
