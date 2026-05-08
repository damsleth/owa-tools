"""Shared config-file I/O for the owa-tools consumer CLIs.

Each consumer's config.py wraps these primitives with its own
CONFIG_PATH and ALLOWED_KEYS tuple. The file format is shell-sourceable
KEY="VALUE" lines, mode 0600, written atomically via tempfile + fsync
+ rename so a crash mid-write never leaves the file truncated.
"""
import os
import tempfile
from pathlib import Path


def parse_lines(text):
    """Parse KEY="VALUE" lines into a dict. No allowlist - callers
    decide whether to filter."""
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


def parse_kv_stream(text, allowed_keys):
    """Parse and filter to `allowed_keys`. Used on the write path
    where unknown keys are a config-injection risk; reads (load_config)
    preserve unknown keys so pre-existing file contents are not silently
    dropped."""
    return {k: v for k, v in parse_lines(text).items() if k in allowed_keys}


def load_config_file(path):
    """Read `path` and return a dict (empty if file missing).
    Caller seeds defaults afterwards as appropriate for the tool."""
    p = Path(path)
    if not p.exists():
        return {}
    return parse_lines(p.read_text())


def save_config(path, config):
    """Atomically rewrite the config file, preserving unknown lines
    and any comments. Write to a sibling temp file, fsync, chmod 0600,
    then rename. Rename within a filesystem is atomic on POSIX, so
    readers see either the old contents or the new ones, never a
    truncated mix."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(p.parent, 0o700)
    lines = []
    existing_keys = set()
    if p.exists():
        for line in p.read_text().splitlines():
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
        prefix='.config.', suffix='.tmp', dir=str(p.parent),
    )
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


def config_set(path, allowed_keys, key, value):
    """Upsert a single KEY=value into the config file, after checking
    against the per-tool allowlist."""
    if key not in allowed_keys:
        raise ValueError(f'unknown config key: {key}')
    current = {}
    p = Path(path)
    if p.exists():
        current = parse_kv_stream(p.read_text(), allowed_keys)
    current[key] = value
    save_config(p, current)
