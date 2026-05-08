"""Token acquisition. Audience configurable per call.

owa-graph is the multi-audience consumer. `--audience <name>` retargets
at any FOCI audience owa-piggy knows about, so this module takes the
audience as an argument and resolves the API base URL accordingly.

Thin wrapper over owa_core.auth - the substance lives there. Per-tool
state (the once-per-process version cache) stays here so tests can
monkeypatch this module's `_owa_piggy_version_checked` and `subprocess`
at the per-tool boundary they were written against.
"""
import shutil
import subprocess  # noqa: F401  (kept so tests can monkeypatch auth_mod.subprocess.run)
import sys

from owa_core import auth as _core
from owa_core.auth import MIN_OWA_PIGGY_VERSION  # noqa: F401

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

_owa_piggy_version_checked = False


def _owa_piggy_available():
    return shutil.which('owa-piggy') is not None


def _parse_version(s):
    return _core.parse_version(s)


def _check_owa_piggy_version():
    global _owa_piggy_version_checked
    if _owa_piggy_version_checked:
        return True
    _owa_piggy_version_checked = True
    return _core.check_owa_piggy_version(TOOL_NAME)


def _log_token_remaining(access, debug):
    _core.log_token_remaining(access, debug)


def _refresh_via_owa_piggy(config, audience='graph', debug=False):
    if not _owa_piggy_available():
        print(
            'ERROR: owa-piggy not found in $PATH. Install with: '
            'brew install damsleth/tap/owa-piggy',
            file=sys.stderr,
        )
        return None
    if not _check_owa_piggy_version():
        return None
    return _core.run_piggy_token(config, audience, debug=debug)


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
    access = do_token_refresh(config, audience=audience, debug=debug)
    return _core.setup_or_exit(access, config, TOOL_NAME, api_base)
