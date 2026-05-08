"""Token acquisition. Audience: graph. The OWA SPA scopes carry
Files.ReadWrite.All, which covers /me/drive read + write.

Thin wrapper over owa_core.auth - the substance lives there. Per-tool
state (the once-per-process version cache) stays here so tests can
monkeypatch this module's `_owa_piggy_version_checked` and `subprocess`
at the per-tool boundary they were written against.
"""
import shutil
import subprocess  # noqa: F401  (kept so tests can monkeypatch auth_mod.subprocess.run)
import sys

from owa_core import auth as _core
from owa_core.auth import MIN_OWA_PIGGY_VERSION  # noqa: F401  (re-export)
from owa_core.errors import OwaError, emit_error

TOOL_NAME = 'owa-drive'
AUDIENCE = 'graph'
API_BASE = 'https://graph.microsoft.com/v1.0'

_owa_piggy_version_checked = False


def _owa_piggy_available():
    return shutil.which('owa-piggy') is not None


def _parse_version(s):
    return _core.parse_version(s)


def _check_owa_piggy_version():
    """Verify owa-piggy is recent enough. Cached once-per-process."""
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
