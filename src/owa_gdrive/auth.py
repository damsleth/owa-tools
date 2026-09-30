"""Token acquisition for a google-provider owa-piggy profile.

Audience `gdrive` is deliberately neither `drive` (owa-drive's OneDrive) nor
a real owa-piggy audience: a Google profile ignores it, an AAD profile
rejects it ("unknown audience"), so a Microsoft profile fails loudly.
"""

from owa_core.auth import get_token, resolve_service_profile
from owa_core.errors import AuthExpiredError, UsageError

TOOL_NAME = 'owa-gdrive'
AUDIENCE = 'gdrive'
SERVICE = 'google'
API_BASE = 'https://www.googleapis.com/drive/v3'


def resolve_profile(config):
    return resolve_service_profile(
        config, tool_name=TOOL_NAME, service=SERVICE,
        missing_hint='run: owa-piggy setup --profile <alias> --google',
    )


def setup_auth(config, debug=False):
    profile = resolve_profile(config)
    try:
        token = get_token(tool_name=TOOL_NAME, audience=AUDIENCE, profile=profile, debug=debug)
    except AuthExpiredError as error:
        if 'unknown audience' in error.message:
            raise UsageError(f'profile {profile!r} is not a Google profile') from error
        raise
    return token.access_token, API_BASE
