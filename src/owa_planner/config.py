"""Config file I/O for owa-planner.

KEY="VALUE" lines, shell-sourceable for symmetry with the rest of the suite.
owa-planner holds no secrets - only an optional profile alias and a default
plan id. The on-disk file is 0600.

Mechanics live in owa_core.config; this file just declares the per-tool path
and allowlist.
"""
import os
from pathlib import Path

from owa_core import config as _core

CONFIG_PATH = Path(
    os.environ.get('XDG_CONFIG_HOME') or str(Path.home() / '.config')
) / 'owa-planner' / 'config'

ALLOWED_KEYS = (
    'owa_piggy_profile',
    'default_plan',
    'debug',
)


def load_config():
    return _core.load_config_file(CONFIG_PATH)


def save_config(config):
    _core.save_config(CONFIG_PATH, config)


def config_set(key, value):
    _core.config_set(CONFIG_PATH, ALLOWED_KEYS, key, value)
