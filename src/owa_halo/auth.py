"""owa-piggy token + Halo host for owa-halo.

A Halo profile in owa-piggy (`setup --halo <host>`) holds Halo's own refresh
token; the broker returns an opaque bearer plus the tenant `host`.
"""

from owa_core.auth import get_profiles, get_token
from owa_core.errors import AuthExpiredError, UsageError

AUDIENCE = 'halo'
PROFILE_TYPE = 'halo'


def resolve_profile(config):
    """Explicit --profile wins; otherwise the one Halo profile in the broker."""
    explicit = (config.get('owa_piggy_profile') or '').strip()
    if explicit:
        return explicit
    halos = [p.alias for p in get_profiles(tool_name='owa-halo') if p.type == PROFILE_TYPE and p.has_config]
    if len(halos) == 1:
        return halos[0]
    if not halos:
        raise UsageError('no Halo profile; run: owa-piggy setup --profile <alias> --halo <tenant>.haloitsm.com')
    raise UsageError(f'several Halo profiles ({", ".join(halos)}); pick one with --profile')


def setup_auth(config, debug=False):
    """Return (access_token, base_url)."""
    profile = resolve_profile(config)
    try:
        token = get_token(tool_name='owa-halo', audience=AUDIENCE, profile=profile, debug=debug)
    except AuthExpiredError as error:
        # An AAD profile rejects the 'halo' audience it has never heard of.
        if 'unknown audience' in error.message:
            raise UsageError(f'profile {profile!r} is not a Halo profile') from error
        raise
    host = (token.raw or {}).get('host')
    if not host:
        raise UsageError('profile is not a Halo profile, or owa-piggy is too old to report its host')
    return token.access_token, f'https://{host}'
