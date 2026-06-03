"""Token acquisition for owa-vids - a two-audience tool.

The DASH manifest and segments on the regional `*-mediap.svc.ms` host
accept a SharePoint resource token (aud = https://{tenant}.sharepoint.com).
Like owa-sites, that resource is per-tenant, so it is not a static named
owa-piggy audience: the token is minted with `--audience graph --scope
https://{spo_host}/.default` (owa-piggy's explicit --scope override wins).

Unlike the rest of the suite there is no single API_BASE constant here:
the SPO host is parsed out of the source URL at runtime, so auth is
deferred into each command handler rather than minted once in `_main`.

Identity resolution (driveId/itemId/title) rides a plain `graph` token.
"""
from owa_core import auth as _core

TOOL_NAME = 'owa-vids'
GRAPH_AUDIENCE = 'graph'
GRAPH_BASE = 'https://graph.microsoft.com/v1.0'


def spo_scope(spo_host):
    return f'https://{spo_host}/.default'


def get_graph_token(config, debug=False):
    """Mint a plain Graph token (drive-item metadata, /shares resolution)."""
    token = _core.get_token_for_config(
        config, tool_name=TOOL_NAME, audience=GRAPH_AUDIENCE, debug=debug,
    )
    return token.access_token


def get_spo_token(config, spo_host, debug=False):
    """Mint a SharePoint resource token for the tenant host in the source URL."""
    token = _core.get_token_for_config(
        config, tool_name=TOOL_NAME, audience=GRAPH_AUDIENCE,
        scope=spo_scope(spo_host), debug=debug,
    )
    return token.access_token


def make_spo_refresh(config, spo_host, debug=False):
    """Build the `token_holder["refresh"]` callable for the segment loop.

    The access_token baked into segment URLs expires ~80 minutes in; the
    download loop calls this once on 401/403 to mint a fresh SPO token
    mid-download and retry.
    """
    profile = (config.get('owa_piggy_profile') or '').strip() or None

    def refresh():
        return _core.get_token(
            tool_name=TOOL_NAME, audience=GRAPH_AUDIENCE,
            profile=profile, scope=spo_scope(spo_host), debug=debug,
        ).access_token

    return refresh
