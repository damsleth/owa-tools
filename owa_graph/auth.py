"""Token acquisition. Audience configurable per call.

owa-graph is the multi-audience consumer. `--audience <name>` retargets
at any FOCI audience owa-piggy knows about, so this module takes the
audience as an argument and resolves the API base URL accordingly.
"""
import sys

from owa_core import auth as _core
from owa_core.errors import OwaError, emit_error

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
    audiences. Unknown audiences exit the process - typos here would
    otherwise produce a confusing 401/404 against a hand-built URL.
    """
    if audience == 'graph':
        return GRAPH_BETA_BASE if beta else AUDIENCE_API_BASE['graph']
    base = AUDIENCE_API_BASE.get(audience)
    if not base:
        known = ', '.join(sorted(AUDIENCE_API_BASE))
        print(
            f'ERROR: unknown audience {audience!r}. Known: {known}',
            file=sys.stderr,
        )
        sys.exit(1)
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
    try:
        token = _core.get_token_for_config(
            config, tool_name=TOOL_NAME, audience=audience, debug=debug,
        )
    except OwaError as error:
        sys.exit(emit_error(error))
    return token.access_token, api_base
