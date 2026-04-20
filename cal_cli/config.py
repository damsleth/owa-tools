"""Config file I/O for cal-cli.

File format is KEY="VALUE" lines, shell-sourceable for backward
compatibility with the old zsh script. Refresh tokens rotate on every
exchange, so a partial write here would corrupt the only live token and
force the user to reseed via owa-piggy. All writes go through a temp
file + fsync + rename.
"""
import os
import tempfile
from pathlib import Path

CONFIG_PATH = Path(
    os.environ.get('XDG_CONFIG_HOME') or str(Path.home() / '.config')
) / 'cal-cli' / 'config'

# Keys we recognise. Parsing an unknown key out of the file is fine (we
# preserve it verbatim), but we never write unknown keys from user input.
ALLOWED_KEYS = (
    'OUTLOOK_REFRESH_TOKEN',
    'OUTLOOK_TENANT_ID',
    'OUTLOOK_APP_CLIENT_ID',
    'default_timezone',
    'debug',
)

DEFAULT_TIMEZONE = 'W. Europe Standard Time'


def parse_kv_stream(text):
    """Parse KEY=value (or KEY="value") lines. Only recognises known
    cal-cli keys; writes for unknown keys are silently dropped."""
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, _, v = line.partition('=')
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k in ALLOWED_KEYS and v:
            out[k] = v
    return out


def load_config():
    """Returns a dict merging the on-disk config with env-var overrides.

    Precedence: environment variables > on-disk config > defaults. Unlike
    owa-piggy we do not track a 'persist' flag - cal-cli always persists
    a rotated refresh token, since cal-cli is only useful when run
    interactively against a configured profile.
    """
    config = {}
    if CONFIG_PATH.exists():
        for line in CONFIG_PATH.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, _, v = line.partition('=')
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k and v:
                config[k] = v
    for key in ('OUTLOOK_REFRESH_TOKEN', 'OUTLOOK_TENANT_ID', 'OUTLOOK_APP_CLIENT_ID'):
        if os.environ.get(key):
            config[key] = os.environ[key]
    config.setdefault('default_timezone', DEFAULT_TIMEZONE)
    return config


def save_config(config):
    """Atomically rewrite the config file, preserving unknown lines.

    Write to a sibling temp file, fsync, chmod 0600, then rename. Rename
    within a filesystem is atomic on POSIX, so readers see either the
    old contents or the new ones, never a truncated mix.
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

    fd, tmp_path = tempfile.mkstemp(
        prefix='.config.', suffix='.tmp', dir=str(CONFIG_PATH.parent)
    )
    tmp = Path(tmp_path)
    try:
        os.chmod(tmp, 0o600)
        with os.fdopen(fd, 'w') as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, CONFIG_PATH)
    except Exception:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
        raise


def config_set(key, value):
    """Upsert a single KEY=value into the config file."""
    if key not in ALLOWED_KEYS:
        raise ValueError(f'unknown config key: {key}')
    current = {}
    if CONFIG_PATH.exists():
        current = parse_kv_stream(CONFIG_PATH.read_text())
    current[key] = value
    save_config(current)
