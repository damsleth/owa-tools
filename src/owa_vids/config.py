"""Config file I/O for owa-vids.

KEY="VALUE" lines, mostly shell-sourceable. owa-vids holds no secrets -
only an optional profile alias and the cached media region host
(`*-mediap.svc.ms`). The region is tenant-wide but differs per profile,
so it is cached per profile in the `regions` JSON map (see get_region /
set_region). The region is learned automatically (item thumbnails name the
host) or from a pasted videomanifest URL. The on-disk file is 0600.

Mechanics live in owa_core.config; this file declares the per-tool path
and allowlist.
"""
import json
import os
from pathlib import Path

from owa_core import config as _core
from owa_core.errors import UsageError

CONFIG_PATH = Path(
    os.environ.get('XDG_CONFIG_HOME') or str(Path.home() / '.config')
) / 'owa-vids' / 'config'

ALLOWED_KEYS = (
    'owa_piggy_profile',
    'regions',    # JSON map {profile: mediap-host} - tenants differ per profile
    'debug',
)


def _profile(config):
    """Active owa-piggy profile alias, or 'default' when none is pinned."""
    return (config.get('owa_piggy_profile') or '').strip() or 'default'


def _regions(config):
    try:
        return json.loads(config.get('regions') or '{}')
    except ValueError:
        return {}


def get_region(config):
    """Cached media region for the active profile."""
    return _regions(config).get(_profile(config))


def set_region(config, region):
    """Cache the media region under the active profile, persisting to disk."""
    regions = _regions(config)
    regions[_profile(config)] = region
    blob = json.dumps(regions, separators=(',', ':'))
    config_set('regions', blob)
    config['regions'] = blob


def load_config():
    return _core.load_config_file(CONFIG_PATH)


def config_set(key, value):
    try:
        _core.config_set(CONFIG_PATH, ALLOWED_KEYS, key, value)
    except ValueError as exc:
        raise UsageError(str(exc))
