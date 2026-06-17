"""Config file I/O for owa-cal.

KEY="VALUE" lines, shell-sourceable for symmetry with owa-mail and
owa-piggy. owa-cal holds no secrets - only an optional profile alias
and a default timezone. The on-disk file is chmod 0600.

Mechanics live in owa_core.config; this file just declares the
per-tool path, allowlist, and defaults.
"""
import os
from pathlib import Path

from owa_core import config as _core

CONFIG_PATH = Path(
    os.environ.get('XDG_CONFIG_HOME') or str(Path.home() / '.config')
) / 'owa-cal' / 'config'

ALLOWED_KEYS = (
    'owa_piggy_profile',
    'default_timezone',
    'debug',
    'tui_reading_pane',
    'tui_split_ratio',
    'tui_day_range',
    'tui_show_declined',
    'tui_event_detail',
)

DEFAULT_TIMEZONE = 'W. Europe Standard Time'


def _parse_lines(text):
    return _core.parse_lines(text)


def parse_kv_stream(text):
    return _core.parse_kv_stream(text, ALLOWED_KEYS)


def load_config():
    config = _core.load_config_file(CONFIG_PATH)
    config.setdefault('default_timezone', DEFAULT_TIMEZONE)
    return config


def save_config(config):
    _core.save_config(CONFIG_PATH, config)


def config_set(key, value):
    _core.config_set(CONFIG_PATH, ALLOWED_KEYS, key, value)
