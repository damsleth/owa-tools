"""Token acquisition. Audience: outlook (Outlook REST endpoint).

owa-cal targets `outlook.office.com`, not Microsoft Graph: the OWA SPA
client owa-piggy borrows does NOT carry Calendars.ReadWrite on the
Graph audience - OWA itself calls Outlook REST for calendar.

Thin wrapper over owa_core.auth - see owa_drive/auth.py for the
"""
import sys

from owa_core import auth as _core
from owa_core.errors import OwaError, emit_error

TOOL_NAME = 'owa-cal'
AUDIENCE = 'outlook'
API_BASE = 'https://outlook.office.com/api/v2.0'

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
