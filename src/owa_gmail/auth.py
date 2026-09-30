"""Token acquisition for a google-provider owa-piggy profile.

Audience `gmail` is deliberately *not* an owa-piggy audience name: a Google
profile ignores the audience (its scopes are fixed at consent time), while an
AAD profile rejects it with "unknown audience" - so pointing owa-gmail at an
M365 profile fails loudly instead of minting a useless Graph token.
"""

from owa_core.auth import get_token, resolve_service_profile
from owa_core.errors import AuthExpiredError, UsageError

TOOL_NAME = 'owa-gmail'
AUDIENCE = 'gmail'
SERVICE = 'google'
API_BASE = 'https://gmail.googleapis.com/gmail/v1/users/me'


def resolve_profile(config):
    return resolve_service_profile(
        config, tool_name=TOOL_NAME, service=SERVICE,
        missing_hint='run: owa-piggy setup --profile <alias> --google',
    )


def _token(config, debug):
    profile = resolve_profile(config)
    try:
        return get_token(tool_name=TOOL_NAME, audience=AUDIENCE, profile=profile, debug=debug)
    except AuthExpiredError as error:
        if 'unknown audience' in error.message:
            raise UsageError(f'profile {profile!r} is not a Google profile') from error
        raise


def setup_auth(config, debug=False):
    return _token(config, debug).access_token, API_BASE
