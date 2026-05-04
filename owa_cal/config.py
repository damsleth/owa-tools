"""Config file I/O for owa-cal.

File format is KEY="VALUE" lines, shell-sourceable for symmetry with
owa-mail and owa-piggy and backward compat with the old zsh script.
owa-cal holds no secrets - only an optional profile alias and a
default timezone. The on-disk file is chmod 0600 anyway as a hygiene
default.
"""
import os
from pathlib import Path

CONFIG_PATH = Path(
    os.environ.get('XDG_CONFIG_HOME') or str(Path.home() / '.config')
) / 'owa-cal' / 'config'

# Keys we recognise. Parsing an unknown key out of the file is fine (we
# preserve it verbatim), but we never write unknown keys from user input.
ALLOWED_KEYS = (
    'owa_piggy_profile',
    'default_timezone',
    'debug',
    'webcal_url',
)

DEFAULT_TIMEZONE = 'W. Europe Standard Time'


def _parse_lines(text):
    """Parse KEY=value (or KEY="value") lines into a dict. No key
    allowlist - callers decide whether to filter."""
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
    """Parse KEY=value lines, dropping anything outside ALLOWED_KEYS.
    Used on the write path to filter user input. Reads (load_config)
    preserve unknown keys so pre-existing file contents are not
    silently dropped."""
    return {k: v for k, v in _parse_lines(text).items() if k in ALLOWED_KEYS}


def load_config():
    """Returns a dict reflecting the on-disk config, with the
    default_timezone fallback applied.

    No env-var pickup: owa-cal's only knobs (`owa_piggy_profile`,
    `default_timezone`) live in the config file, and `--profile` on
    the CLI is the override path for the former.
    """
    config = {}
    if CONFIG_PATH.exists():
        config.update(_parse_lines(CONFIG_PATH.read_text()))
    config.setdefault('default_timezone', DEFAULT_TIMEZONE)
    return config


def save_config(config):
    """Rewrite the config file, preserving unknown lines.

    Atomicity is not required (no secret rotation here), but we still
    chmod 0600 on the way out as a hygiene default.
    """
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
    """Upsert a single KEY=value into the config file."""
    if key not in ALLOWED_KEYS:
        raise ValueError(f'unknown config key: {key}')
    current = {}
    if CONFIG_PATH.exists():
        current = parse_kv_stream(CONFIG_PATH.read_text())
    current[key] = value
    save_config(current)
