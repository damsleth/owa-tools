"""Config file I/O for owa-ado.

KEY="VALUE" lines, shell-sourceable, chmod 0600. Stores the owa-piggy
profile alias plus the default Azure DevOps organisation and project so
the common case (`owa-ado wi`) needs no flags.

Mechanics live in owa_core.config; this file declares the per-tool path
and allowlist only.
"""
import os
import tempfile
from pathlib import Path

from owa_core import config as _core

CONFIG_PATH = Path(
    os.environ.get('XDG_CONFIG_HOME') or str(Path.home() / '.config')
) / 'owa-ado' / 'config'

ALLOWED_KEYS = (
    'owa_piggy_profile',
    'ado_org',
    'ado_project',
    'debug',
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


def config_unset(key):
    """Remove one key from the config. Returns True if it was present.

    `save_config` preserves any line whose key isn't in the dict, so dropping
    a key means rewriting from the remaining allowed pairs only.
    """
    if key not in ALLOWED_KEYS:
        raise ValueError(f'unknown config key: {key}')
    p = Path(CONFIG_PATH)
    if not p.exists():
        return False
    current = parse_kv_stream(p.read_text())
    if key not in current:
        return False
    del current[key]
    _rewrite(current)
    return True


def config_clear():
    """Drop all owa-ado config keys. Returns the count removed."""
    p = Path(CONFIG_PATH)
    if not p.exists():
        return 0
    current = parse_kv_stream(p.read_text())
    _rewrite({})
    return len(current)


def _rewrite(pairs):
    """Atomically rewrite the config to exactly `pairs` (allowed keys only)."""
    p = Path(CONFIG_PATH)
    p.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(p.parent, 0o700)
    payload = ''.join(f'{k}="{v}"\n' for k, v in pairs.items())
    fd, tmp_path = tempfile.mkstemp(prefix='.config.', suffix='.tmp', dir=str(p.parent))
    tmp = Path(tmp_path)
    try:
        os.chmod(tmp, 0o600)
        with os.fdopen(fd, 'w') as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)
    except Exception:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
        raise
