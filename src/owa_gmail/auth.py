"""Token acquisition for a google-provider owa-piggy profile.

Audience `gmail` is deliberately *not* an owa-piggy audience name: a Google
profile ignores the audience (its scopes are fixed at consent time), while an
AAD profile rejects it with "unknown audience" - so pointing owa-gmail at an
M365 profile fails loudly instead of minting a useless Graph token.
"""

from owa_core.auth import get_profiles, get_token
from owa_core.errors import AuthExpiredError, UsageError

TOOL_NAME = 'owa-gmail'
AUDIENCE = 'gmail'
SERVICE = 'google'
API_BASE = 'https://gmail.googleapis.com/gmail/v1/users/me'


def resolve_profile(config):
    """Explicit --profile / pinned profile wins; else the default profile if
    it is a Google one; else the one profile that is."""
    explicit = (config.get('owa_piggy_profile') or '').strip()
    if explicit:
        return explicit
    rows = [p for p in get_profiles(tool_name=TOOL_NAME) if SERVICE in p.services and p.has_config]
    default = next((p.alias for p in rows if p.default), None)
    if default:
        return default
    if len(rows) == 1:
        return rows[0].alias
    if not rows:
        raise UsageError('no Google profile; run: owa-piggy setup --profile <alias> --google')
    raise UsageError(f'several Google profiles ({", ".join(p.alias for p in rows)}); pick one with --profile')


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
