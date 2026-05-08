"""Token acquisition. Audience: graph. The OWA SPA scopes carry
Files.ReadWrite.All, which covers /me/drive read + write.
"""
import sys

from owa_core import auth as _core
from owa_core.errors import OwaError, emit_error

TOOL_NAME = 'owa-drive'
AUDIENCE = 'graph'
API_BASE = 'https://graph.microsoft.com/v1.0'

def _log_token_remaining(access, debug):
    _core.log_token_remaining(access, debug)


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
    try:
        token = _core.get_token_for_config(
            config, tool_name=TOOL_NAME, audience=AUDIENCE, debug=debug,
        )
    except OwaError as error:
        sys.exit(emit_error(error))
    return token.access_token, API_BASE
