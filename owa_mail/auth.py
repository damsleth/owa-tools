"""Token acquisition. Audience: outlook (Outlook REST endpoint).

owa-mail targets `outlook.office.com`, matching owa-cal. The OWA SPA
client owa-piggy borrows carries Mail.ReadWrite on the Outlook
audience.

Thin wrapper over owa_core.auth - see owa_drive/auth.py for the
duplicated boilerplate rationale.
"""
import shutil
import subprocess  # noqa: F401
import sys

from owa_core import auth as _core
from owa_core.auth import MIN_OWA_PIGGY_VERSION  # noqa: F401
from owa_core.errors import OwaError, emit_error

TOOL_NAME = 'owa-mail'
AUDIENCE = 'outlook'
API_BASE = 'https://outlook.office.com/api/v2.0'

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
    try:
        token = _core.get_token_for_config(
            config, tool_name=TOOL_NAME, audience=AUDIENCE, debug=debug,
        )
    except OwaError as error:
        sys.exit(emit_error(error))
    return token.access_token, API_BASE
