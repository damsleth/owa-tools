"""Config file I/O for cal-cli.

File format is KEY="VALUE" lines, shell-sourceable for backward
compatibility with the old zsh script. On the app-registration path
refresh tokens rotate on every exchange, so a partial write here would
corrupt the only live token; all writes go through a temp file + fsync
+ rename. On the owa-piggy path cal-cli holds no secrets, just an
optional profile alias string.
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
    'owa_piggy_profile',
    'default_timezone',
    'debug',
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
    Used on the write path where unknown keys are a config-injection
    risk (e.g. piped input). Reads (load_config) preserve unknown keys
    so pre-existing file contents are not silently dropped."""
    return {k: v for k, v in _parse_lines(text).items() if k in ALLOWED_KEYS}


def load_config():
    """Returns a dict merging the on-disk config with env-var overrides.

    Precedence: environment variables > on-disk config > defaults. Only
    the app-registration client_id is env-overrideable; the refresh
    token and tenant id on the app-reg path live exclusively in the
    config file. The owa-piggy path reads no secrets out of the
    environment (OWA_PROFILE reaches owa-piggy directly via inherited
    env).
    """
    config = {}
    if CONFIG_PATH.exists():
        config.update(_parse_lines(CONFIG_PATH.read_text()))
    if os.environ.get('OUTLOOK_APP_CLIENT_ID'):
        config['OUTLOOK_APP_CLIENT_ID'] = os.environ['OUTLOOK_APP_CLIENT_ID']
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
