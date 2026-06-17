"""Token acquisition. Audience configurable per call.

owa-graph is the multi-audience consumer. `--audience <name>` retargets
at any FOCI audience owa-piggy knows about, so this module takes the
audience as an argument and resolves the API base URL accordingly.
"""
import sys

from owa_core import auth as _core
from owa_core.errors import OwaError, UsageError, emit_error

TOOL_NAME = 'owa-graph'

# Audience short name -> API base URL we issue requests against. Mirrors
# owa-piggy/owa_piggy/scopes.py:KNOWN_AUDIENCES, but where that table
# returns the *AAD audience host* (used to compose `<host>/.default`
# scopes), this one returns the *API base* including the version path.
AUDIENCE_API_BASE = {
    'graph':      'https://graph.microsoft.com/v1.0',
    'outlook':    'https://outlook.office.com/api/v2.0',
    'outlook365': 'https://outlook.office365.com/api/v2.0',
    'teams':      'https://api.spaces.skype.com',
    'ic3':        'https://ic3.teams.office.com',
    'csa':        'https://chatsvcagg.teams.microsoft.com',
    'presence':   'https://presence.teams.microsoft.com',
    'uis':        'https://uis.teams.microsoft.com',
    'azure':      'https://management.azure.com',
    'keyvault':   'https://vault.azure.net',
    'storage':    'https://storage.azure.com',
    'sql':        'https://database.windows.net',
    'substrate':  'https://substrate.office.com',
    'manage':     'https://manage.office.com/api/v1.0',
    'powerbi':    'https://api.powerbi.com/v1.0',
    'flow':       'https://service.flow.microsoft.com',
    'devops':     'https://app.vssps.visualstudio.com',
}

# Audience short name -> one-liner description. Mirrors the prose owa-piggy
# prints for `owa-piggy audiences` (owa_piggy/scopes.py:KNOWN_AUDIENCES).
# Covers every key in AUDIENCE_API_BASE.
AUDIENCE_DESC = {
    'graph':      'Microsoft Graph (default)',
    'outlook':    'Outlook REST',
    'outlook365': 'Outlook REST (alternate)',
    'teams':      'Microsoft Teams middle-tier (mt/part, Skype audience)',
    'ic3':        'Microsoft Teams chatsvc / asyncgw (modern)',
    'csa':        'Microsoft Teams chat-service aggregator (updates, chatsAndTeams)',
    'presence':   'Microsoft Teams presence / pubsub (ups)',
    'uis':        'Microsoft Teams user/notification settings (nss)',
    'azure':      'Azure Resource Manager',
    'keyvault':   'Azure Key Vault',
    'storage':    'Azure Blob/Table/Queue Storage',
    'sql':        'Azure SQL',
    'substrate':  'Office Substrate (Copilot, search)',
    'manage':     'Office Management API',
    'powerbi':    'Power BI',
    'flow':       'Power Automate',
    'devops':     'Azure DevOps',
}

GRAPH_BETA_BASE = 'https://graph.microsoft.com/beta'

def _log_token_remaining(access, debug):
    _core.log_token_remaining(access, debug)


def _refresh_via_owa_piggy(config, audience='graph', debug=False):
    try:
        token = _core.get_token_for_config(
            config, tool_name=TOOL_NAME, audience=audience, debug=debug,
        )
    except OwaError as error:
        emit_error(error)
        return None
    return token.access_token


def resolve_api_base(audience, beta=False):
    """Audience short-name -> API base URL.

    `--beta` only flips Graph's base; it has no effect on other
    audiences. Unknown audiences raise a usage error.
    """
    if audience == 'graph':
        return GRAPH_BETA_BASE if beta else AUDIENCE_API_BASE['graph']
    base = AUDIENCE_API_BASE.get(audience)
    if not base:
        known = ', '.join(sorted(AUDIENCE_API_BASE))
        raise UsageError(f'unknown audience {audience!r}. Known: {known}')
    if beta:
        print(
            f'WARN: --beta has no effect on audience {audience!r}; ignoring',
            file=sys.stderr,
        )
    return base


def do_token_refresh(config, audience='graph', debug=False):
    return _refresh_via_owa_piggy(config, audience=audience, debug=debug)


def setup_auth(config, audience='graph', beta=False, debug=False):
    api_base = resolve_api_base(audience, beta=beta)
    token = _core.get_token_for_config(
        config, tool_name=TOOL_NAME, audience=audience, debug=debug,
    )
    return token.access_token, api_base
