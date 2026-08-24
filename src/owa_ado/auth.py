"""Token acquisition for owa-ado. Audience: devops.

The `devops` audience resolves (in owa-piggy) to the Azure DevOps
resource scope, minting an access token with `aud=499b84ac-1321-427f-
aa17-267ca6975798`. The profile must have been seeded against the Azure
DevOps client (owa-piggy's non-FOCI capture path) - the FOCI Outlook
client cannot obtain a DevOps token (AADSTS65002 preauth wall).

Unlike the Graph tools, the API base is per-organisation
(`https://dev.azure.com/<org>`), so this module returns only the access
token; the CLI layer builds the org-scoped base from config.
"""
from owa_core import auth as _core
from owa_core.errors import OwaError, emit_error

TOOL_NAME = 'owa-ado'
AUDIENCE = 'devops'
ADO_BASE = 'https://dev.azure.com'


def org_base(org):
    """Org-scoped REST base, e.g. https://dev.azure.com/ACME-Corp."""
    return f'{ADO_BASE}/{org.strip("/")}'


def _log_token_remaining(access, debug):
    _core.log_token_remaining(access, debug)


def _refresh_via_owa_piggy(config, debug=False):
    try:
        token = _core.get_token_for_config(
            config, tool_name=TOOL_NAME, audience=AUDIENCE, debug=debug,
        )
    except OwaError as error:
        emit_error(error)
        return None
    return token.access_token


def do_token_refresh(config, debug=False):
    return _refresh_via_owa_piggy(config, debug=debug)


def setup_auth(config, debug=False):
    """Return a bare Azure DevOps access token, or raise a typed OwaError.

    The CLI pairs this with `org_base(org)` to form the full REST base.
    """
    token = _core.get_token_for_config(
        config, tool_name=TOOL_NAME, audience=AUDIENCE, debug=debug,
    )
    return token.access_token
