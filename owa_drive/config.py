"""Config file I/O for owa-drive.

KEY="VALUE" lines, shell-sourceable. Stores only an optional
`owa_piggy_profile` alias. The on-disk file is chmod 0600.
"""
import os
from pathlib import Path

CONFIG_PATH = Path(
    os.environ.get('XDG_CONFIG_HOME') or str(Path.home() / '.config')
) / 'owa-drive' / 'config'

ALLOWED_KEYS = (
    'owa_piggy_profile',
    'debug',
)


def _parse_lines(text):
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, _, v = line.partition('=')
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and v:
            out[k] = v
    return out


def parse_kv_stream(text):
    return {k: v for k, v in _parse_lines(text).items() if k in ALLOWED_KEYS}


def load_config():
    config = {}
    if CONFIG_PATH.exists():
        config.update(_parse_lines(CONFIG_PATH.read_text()))
    return config


def save_config(config):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    lines = []
    existing_keys = set()
    if CONFIG_PATH.exists():
        for line in CONFIG_PATH.read_text().splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith('#') and '=' in stripped:
                k = stripped.split('=', 1)[0].strip()
                if k in config:
                    lines.append(f'{k}="{config[k]}"')
                    existing_keys.add(k)
                    continue
            lines.append(line)
    for k, v in config.items():
        if k not in existing_keys:
            lines.append(f'{k}="{v}"')
    payload = '\n'.join(lines) + '\n'
    CONFIG_PATH.write_text(payload)
    CONFIG_PATH.chmod(0o600)


def config_set(key, value):
    if key not in ALLOWED_KEYS:
        raise ValueError(f'unknown config key: {key}')
    current = {}
    if CONFIG_PATH.exists():
        current = parse_kv_stream(CONFIG_PATH.read_text())
    current[key] = value
    save_config(current)
