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
    'tui_reading_pane',
    'tui_split_ratio',
    'tui_sort_by',
    'tui_date_format',
    'tui_date_custom',
)


def _parse_lines(text):
    return _core.parse_lines(text)


def parse_kv_stream(text):
    return _core.parse_kv_stream(text, ALLOWED_KEYS)


def load_config():
    return _core.load_config_file(CONFIG_PATH)


def save_config(config):
    _core.save_config(CONFIG_PATH, config)


def config_set(key, value):
    _core.config_set(CONFIG_PATH, ALLOWED_KEYS, key, value)
