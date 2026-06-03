"""Config file I/O for owa-vids.

KEY="VALUE" lines, shell-sourceable for symmetry with the rest of the
suite. owa-vids holds no secrets - only an optional profile alias and the
cached media region host (`*-mediap.svc.ms`, tenant-wide, learned from the
first --manifest-url run). The on-disk file is 0600.

Mechanics live in owa_core.config; this file declares the per-tool path
and allowlist, plus a one-time migration from the standalone script's
`~/.config/owa-vids/config.json` ({"profile": ..., "region": ...}).
"""
import json
import os
import sys
from pathlib import Path

from owa_core import config as _core
from owa_core.errors import UsageError

CONFIG_PATH = Path(
    os.environ.get('XDG_CONFIG_HOME') or str(Path.home() / '.config')
) / 'owa-vids' / 'config'

ALLOWED_KEYS = (
    'owa_piggy_profile',
    'region',
    'debug',
)

# Standalone-script JSON key -> suite config key.
_LEGACY_KEY_MAP = {'profile': 'owa_piggy_profile', 'region': 'region'}


def _migrate_json_config():
    """One-time import of the standalone script's config.json.

    Reads the old JSON file (if present and no suite-format file exists
    yet), rewrites the known keys in KEY="VALUE" form, then deletes the
    old file. Failures are non-fatal: the tool keeps working with
    defaults and warns once on stderr.
    """
    if CONFIG_PATH.exists():
        return
    legacy = CONFIG_PATH.parent / 'config.json'
    if not legacy.exists():
        return
    try:
        old = json.loads(legacy.read_text())
    except (OSError, ValueError):
        return
    migrated = {
        new_key: str(old[old_key])
        for old_key, new_key in _LEGACY_KEY_MAP.items()
        if isinstance(old, dict) and old.get(old_key)
    }
    try:
        if migrated:
            _core.save_config(CONFIG_PATH, migrated)
        legacy.unlink()
    except OSError:
        print(
            f'owa-vids: warning: could not migrate legacy {legacy}; '
            'remove it manually or fix permissions',
            file=sys.stderr,
        )
        return
    if migrated:
        print(f'owa-vids: migrated legacy config.json -> {CONFIG_PATH}', file=sys.stderr)


def load_config():
    _migrate_json_config()
    return _core.load_config_file(CONFIG_PATH)


def save_config(config):
    _core.save_config(CONFIG_PATH, config)


def config_set(key, value):
    try:
        _core.config_set(CONFIG_PATH, ALLOWED_KEYS, key, value)
    except ValueError as exc:
        raise UsageError(str(exc))
