"""Auth helpers for owa-places."""

from owa_core.auth import get_token_for_config

AUDIENCE = 'outlook'
SCOPE = 'Calendars.Read'


def setup_auth(config, debug=False):
    token = get_token_for_config(config, tool_name='owa-places', audience=AUDIENCE, scope=SCOPE, debug=debug)
    return token.access_token, 'https://outlook.office.com'
