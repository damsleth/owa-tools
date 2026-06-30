"""Config file I/O for owa-sites.

KEY="VALUE" lines, shell-sourceable for symmetry with the rest of the suite.
owa-sites holds no secrets - only an optional profile alias, a pinned
SharePoint host (to skip discovery), and a default site. The on-disk file is
0600.

Mechanics live in owa_core.config; this file just declares the per-tool path
and allowlist.
"""
import os
from pathlib import Path

from owa_core import config as _core
from owa_core.errors import UsageError

CONFIG_PATH = Path(
    os.environ.get('XDG_CONFIG_HOME') or str(Path.home() / '.config')
) / 'owa-sites' / 'config'

ALLOWED_KEYS = (
    'owa_piggy_profile',
    'sharepoint_host',
    'default_site',
    'debug',
)


def load_config():
    return _core.load_config_file(CONFIG_PATH)


def save_config(config):
    _core.save_config(CONFIG_PATH, config)


def config_set(key, value):
    _core.config_set(CONFIG_PATH, ALLOWED_KEYS, key, value)


def config_unset(key):
    """Remove a single allowlisted key from the config file (no-op if absent).

    `_core.save_config` preserves any line whose key is still in the dict, so
    deleting a key means rewriting from the filtered dict rather than handing
    the key to save_config. Unknown lines/comments survive because the file is
    re-read minus the dropped key.
    """
    if key not in ALLOWED_KEYS:
        raise UsageError(f'unknown config key: {key}')
    p = Path(CONFIG_PATH)
    if not p.exists():
        return
    kept = [ln for ln in p.read_text().splitlines()
            if ln.split('=', 1)[0].strip() != key]
    p.write_text('\n'.join(kept) + ('\n' if kept else ''))


def config_clear():
    """Delete the config file entirely (no-op if it does not exist)."""
    Path(CONFIG_PATH).unlink(missing_ok=True)
