"""Config file I/O for owa-mail.

KEY="VALUE" lines, shell-sourceable for symmetry with owa-cal and
owa-piggy. owa-mail holds no secrets - only an optional profile alias.
The on-disk file is chmod 0600.

Mechanics live in owa_core.config; this file just declares the
per-tool path and allowlist.
"""
import os
from pathlib import Path

from owa_core import config as _core

CONFIG_PATH = Path(
    os.environ.get('XDG_CONFIG_HOME') or str(Path.home() / '.config')
) / 'owa-mail' / 'config'

ALLOWED_KEYS = (
    'owa_piggy_profile',
    'debug',
)


def load_config():
    return _core.load_config_file(CONFIG_PATH)


def config_set(key, value):
    _core.config_set(CONFIG_PATH, ALLOWED_KEYS, key, value)
