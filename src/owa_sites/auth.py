"""Token acquisition for owa-sites - a two-audience tool.

owa-sites talks to the SharePoint REST API at `https://{tenant}.sharepoint.com`.
That host's tokens carry `Sites.FullControl.All` + `Files.ReadWrite.All` and are
minted by overriding the `--scope` to the per-tenant SharePoint resource (the
shared graph audience's default scope does NOT grant SharePoint). Verified live
2026-06-01: `owa-piggy token --scope 'https://{host}/.default'` yields a token
whose `aud` is the SharePoint resource, and `GET {host}/sites/{x}/_api/web` 200s.

Because the SharePoint resource is per-tenant, it is not a static named owa-piggy
audience. The flow is:

  1. mint a normal `graph` token, read `GET /organization?$select=verifiedDomains`
     to derive the host (`<initial-domain-prefix>.sharepoint.com`); OR use a
     pinned `sharepoint_host` from config to skip discovery, then
  2. mint the SharePoint token via `get_token(audience='graph', scope=<host url>)`
     - owa-piggy's `--scope` override wins, so the resource is SharePoint.

The Graph `/sites` API is NOT used: the shared token lacks `Sites.Read.All`, so
`/sites` 403s. SharePoint REST on the resource token is the working door.
"""

from owa_core import auth as _core
from owa_core import http
from owa_core.errors import InternalError, OwaError, emit_error

TOOL_NAME = 'owa-sites'
GRAPH_AUDIENCE = 'graph'
GRAPH_BASE = 'https://graph.microsoft.com/v1.0'


def _normalize_host(value):
    return (value or '').strip().replace('https://', '').replace('http://', '').strip('/').lower()


def _discover_sp_host(config, debug=False):
    """Derive `{prefix}.sharepoint.com` from the tenant's initial onmicrosoft
    domain via Microsoft Graph (`Organization.Read.All` on the graph token)."""
    token = _core.get_token_for_config(
        config, tool_name=TOOL_NAME, audience=GRAPH_AUDIENCE, debug=debug,
    )
    resp = http.request(
        'GET',
        f'{GRAPH_BASE}/organization?$select=verifiedDomains',
        token=token.access_token,
        debug=debug,
    )
    org = resp.json if isinstance(resp.json, dict) else {}
    for record in org.get('value', []):
        for domain in record.get('verifiedDomains', []):
            name = (domain.get('name') or '')
            if name.lower().endswith('.onmicrosoft.com'):
                return f"{name.split('.', 1)[0].lower()}.sharepoint.com"
    raise InternalError(
        'could not derive the SharePoint host from /organization verifiedDomains',
        remediation='pin it with: owa-sites config --host <tenant>.sharepoint.com',
    )


def resolve_sp_host(config, debug=False):
    host = _normalize_host(config.get('sharepoint_host'))
    if host:
        return host
    return _discover_sp_host(config, debug=debug)


def setup_auth(config, debug=False):
    """Return (access_token, base) where base is `https://{tenant}.sharepoint.com`."""
    host = resolve_sp_host(config, debug=debug)
    scope = f'https://{host}/.default'
    token = _core.get_token_for_config(
        config, tool_name=TOOL_NAME, audience=GRAPH_AUDIENCE, scope=scope, debug=debug,
    )
    return token.access_token, f'https://{host}'


def do_token_refresh(config, debug=False):
    try:
        access, _base = setup_auth(config, debug=debug)
    except OwaError as error:
        emit_error(error)
        return None
    return access
