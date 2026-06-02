"""Token acquisition for owa-teams - a two-audience tool.

owa-teams reads two distinct surfaces, each behind its own owa-piggy audience:

  1. **Graph** (`graph` audience, `https://graph.microsoft.com/v1.0`) for
     enumeration: `/me/joinedTeams`, `/teams/{id}/channels`, `/me/chats`. These
     work on the plain graph token the One Outlook Web client already carries.

  2. **chatsvc / ic3** (`ic3` audience, `https://ic3.teams.office.com`) for
     message *bodies*. Channel + chat message bodies are NOT readable on Graph
     under owa-piggy's FOCI client: `/teams/.../messages` requires
     `ChannelMessage.Read.All`, which AADSTS65002 blocks. The Teams web client
     reads them from the chat service at
     `https://teams.microsoft.com/api/chatsvc/{region}/v1/...` instead, and
     owa-piggy mints an `ic3`-audience bearer that the chat service accepts.
     Verified live 2026-06-02 (crayon profile, emea): an `ic3` bearer returns
     200 on the channel-messages endpoint across every channel tested. No
     skypetoken / authsvc exchange is needed for reads.

The chat service is regional: the path carries a short region segment
(`emea`/`amer`/`apac`/`ind`/...). v1 pins it via `config.teams_region`
(default `emea`); proper resolution (the authsvc `regionGtms.chatService`
round-trip) is a later enhancement - see AGENTS.md.
"""

from owa_core import auth as _core
from owa_core.errors import OwaError, emit_error

TOOL_NAME = 'owa-teams'

GRAPH_AUDIENCE = 'graph'
GRAPH_BASE = 'https://graph.microsoft.com/v1.0'

CHATSVC_AUDIENCE = 'ic3'
CHATSVC_HOST = 'https://teams.microsoft.com'
DEFAULT_REGION = 'emea'


def resolve_region(config):
    region = (config.get('teams_region') or DEFAULT_REGION).strip().lower()
    return region or DEFAULT_REGION


def graph_setup(config, debug=False):
    """Return (access_token, base) for the Graph enumeration surface."""
    token = _core.get_token_for_config(
        config, tool_name=TOOL_NAME, audience=GRAPH_AUDIENCE, debug=debug,
    )
    return token.access_token, GRAPH_BASE


def chatsvc_setup(config, debug=False):
    """Return (access_token, base) for the regional chat service.

    `base` is `https://teams.microsoft.com/api/chatsvc/{region}/v1`; endpoints
    hang off `/users/ME/conversations/...`.
    """
    token = _core.get_token_for_config(
        config, tool_name=TOOL_NAME, audience=CHATSVC_AUDIENCE, debug=debug,
    )
    region = resolve_region(config)
    base = f'{CHATSVC_HOST}/api/chatsvc/{region}/v1'
    return token.access_token, base


def do_graph_refresh(config, debug=False):
    try:
        access, _base = graph_setup(config, debug=debug)
    except OwaError as error:
        emit_error(error)
        return None
    return access
