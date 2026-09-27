"""owa-piggy token + Halo host for owa-halo.

Halo is a service on an owa-piggy profile (`owa-piggy clients add
halo=<url> --profile nc`): the broker holds Halo's own refresh token and
returns an opaque bearer plus the tenant `host` for `--audience halo`.
"""

from owa_core.auth import get_profiles, get_token
from owa_core.errors import AuthExpiredError, UsageError

AUDIENCE = 'halo'
SERVICE = 'halo'


def resolve_profile(config):
    """Explicit --profile wins; else the default profile if it has Halo; else
    the one profile that does."""
    explicit = (config.get('owa_piggy_profile') or '').strip()
    if explicit:
        return explicit
    rows = [p for p in get_profiles(tool_name='owa-halo') if SERVICE in p.services and p.has_config]
    default = next((p.alias for p in rows if p.default), None)
    if default:
        return default
    if len(rows) == 1:
        return rows[0].alias
    if not rows:
        raise UsageError(
            'no profile has Halo; run: owa-piggy clients add '
            'halo=https://<tenant>.haloitsm.com --profile <alias>'
        )
    raise UsageError(f'several profiles have Halo ({", ".join(p.alias for p in rows)}); pick one with --profile')


def setup_auth(config, debug=False):
    """Return (access_token, base_url)."""
    profile = resolve_profile(config)
    try:
        token = get_token(tool_name='owa-halo', audience=AUDIENCE, profile=profile, debug=debug)
    except AuthExpiredError as error:
        # An AAD profile rejects the 'halo' audience it has never heard of.
        if 'unknown audience' in error.message:
            raise UsageError(f'profile {profile!r} has no Halo sign-in') from error
        raise
    host = (token.raw or {}).get('host')
    if not host:
        raise UsageError('profile has no Halo sign-in, or owa-piggy is too old to report its host')
    return token.access_token, f'https://{host}'
