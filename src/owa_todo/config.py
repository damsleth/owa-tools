"""Config file I/O for owa-todo.

KEY="VALUE" lines, shell-sourceable for symmetry with the rest of the
suite. owa-todo holds no secrets - only an optional profile alias, a
default task folder, and a default timezone. The on-disk file is 0600.

Mechanics live in owa_core.config; this file just declares the per-tool
path, allowlist, and defaults.
"""
import os
from pathlib import Path

from owa_core import config as _core

CONFIG_PATH = Path(
    os.environ.get('XDG_CONFIG_HOME') or str(Path.home() / '.config')
) / 'owa-todo' / 'config'

ALLOWED_KEYS = (
    'owa_piggy_profile',
    'default_folder',
    'default_timezone',
    'debug',
)

DEFAULT_TIMEZONE = 'W. Europe Standard Time'


def load_config():
    config = _core.load_config_file(CONFIG_PATH)
    config.setdefault('default_timezone', DEFAULT_TIMEZONE)
    return config


def save_config(config):
    _core.save_config(CONFIG_PATH, config)


def config_set(key, value):
    _core.config_set(CONFIG_PATH, ALLOWED_KEYS, key, value)
