"""Config file I/O for owa-graph.

KEY="VALUE" lines, shell-sourceable. owa-graph holds no secrets - just
an optional profile alias and a default audience. The on-disk file is
chmod 0600.

Mechanics live in owa_core.config; this file just declares the
per-tool path, allowlist, and defaults.
"""
import os
from pathlib import Path

from owa_core import config as _core

CONFIG_PATH = Path(
    os.environ.get('XDG_CONFIG_HOME') or str(Path.home() / '.config')
) / 'owa-graph' / 'config'

ALLOWED_KEYS = (
    'owa_piggy_profile',
    'default_audience',
    'debug',
)

DEFAULT_AUDIENCE = 'graph'


def load_config():
    config = _core.load_config_file(CONFIG_PATH)
    config.setdefault('default_audience', DEFAULT_AUDIENCE)
    return config


def config_set(key, value):
    _core.config_set(CONFIG_PATH, ALLOWED_KEYS, key, value)
