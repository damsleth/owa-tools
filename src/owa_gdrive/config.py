"""Config file I/O for owa-gdrive: only an optional pinned profile alias."""
import os
from pathlib import Path

from owa_core import config as _core

CONFIG_PATH = Path(
    os.environ.get('XDG_CONFIG_HOME') or str(Path.home() / '.config')
) / 'owa-gdrive' / 'config'

ALLOWED_KEYS = (
    'owa_piggy_profile',
    'debug',
)


def load_config():
    return _core.load_config_file(CONFIG_PATH)


def config_set(key, value):
    _core.config_set(CONFIG_PATH, ALLOWED_KEYS, key, value)
