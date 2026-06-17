"""Config file I/O for owa-graph.

KEY="VALUE" lines, shell-sourceable. owa-graph holds no secrets - just
an optional profile alias and a default audience. The on-disk file is
chmod 0600.

Mechanics live in owa_core.config; this file just declares the
per-tool path, allowlist, and defaults.
"""
import os  # noqa: F401  (kept so tests can monkeypatch config_mod.os.replace)
from pathlib import Path

from owa_core import config as _core

CONFIG_PATH = Path(
    os.environ.get('XDG_CONFIG_HOME') or str(Path.home() / '.config')
) / 'owa-graph' / 'config'

ALLOWED_KEYS = (
    'owa_piggy_profile',
    'default_audience',
    'debug',
    # Interactive explorer (owa-graph tui) view settings + bookmarks.
    'graph_tui_reading_pane',
    'graph_tui_split_ratio',
    'graph_tui_pretty_json',
    'graph_tui_scope_warnings',
    'graph_tui_default_audience',
    'graph_tui_default_path',
    'graph_tui_bookmarks',
)

DEFAULT_AUDIENCE = 'graph'


def _parse_lines(text):
    return _core.parse_lines(text)


def parse_kv_stream(text):
    return _core.parse_kv_stream(text, ALLOWED_KEYS)


def load_config():
    config = _core.load_config_file(CONFIG_PATH)
    config.setdefault('default_audience', DEFAULT_AUDIENCE)
    return config


def save_config(config):
    _core.save_config(CONFIG_PATH, config)


def config_set(key, value):
    _core.config_set(CONFIG_PATH, ALLOWED_KEYS, key, value)
