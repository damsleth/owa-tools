"""Local webcal profile store + owa-piggy alias listing.

owa-cal lets the user save named webcal/iCal sources alongside the
OAuth profiles owa-piggy owns. The two stores live in different
files; this module is the merge point.

  ~/.config/owa-cal/profiles.json   {alias: {"webcal_url": "..."}}
  ~/.config/owa-piggy/profiles/...  (owned by owa-piggy; we read its
                                     CLI output, not its files)

The webcal URL is a bearer secret. The JSON file is written 0600 with
a parent directory at 0700, matching the hygiene defaults `config.py`
already enforces. Schema is intentionally permissive: future per-profile
keys can be added without a migration.

Resolution order (the "closest profile wins" rule, see cli.py):
  1. A name set via --profile / OWA_PROFILE / config pin: if it lives
     in profiles.json -> webcal source; otherwise forwarded to piggy.
  2. OWA_CAL_WEBCAL_URL env: ad-hoc, no name, last fallback.
  3. Plain owa-piggy default.
"""
import json
import os
import tempfile
from pathlib import Path

from owa_core import auth as core_auth
from owa_core.errors import OwaError

PROFILES_PATH = Path(
    os.environ.get('XDG_CONFIG_HOME') or str(Path.home() / '.config')
) / 'owa-cal' / 'profiles.json'


def load_local():
    """Read the local profiles file. Returns an empty dict if the file
    is missing, unreadable, or contains malformed JSON - we never
    raise from a read so the CLI can keep functioning in degraded
    mode."""
    if not PROFILES_PATH.exists():
        return {}
    try:
        data = json.loads(PROFILES_PATH.read_text() or '{}')
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def save_local(profiles):
    """Atomic write + chmod 0600. The webcal URL is a bearer secret;
    the parent dir is 0700 too. Mirrors owa_core.config.save_config:
    mkstemp creates the file with mode 0600, fsync hits disk before the
    rename, and the rename is atomic on POSIX."""
    PROFILES_PATH.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(PROFILES_PATH.parent, 0o700)
    payload = json.dumps(profiles, indent=2, sort_keys=True) + '\n'
    fd, tmp_path = tempfile.mkstemp(
        prefix='.profiles.', suffix='.tmp', dir=str(PROFILES_PATH.parent),
    )
    tmp = Path(tmp_path)
    try:
        os.chmod(tmp, 0o600)
        with os.fdopen(fd, 'w') as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, PROFILES_PATH)
    except Exception:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
        raise


def add_local(alias, webcal_url):
    """Upsert an entry. Returns True if newly created, False on update."""
    profiles = load_local()
    new = alias not in profiles
    profiles[alias] = {'webcal_url': webcal_url}
    save_local(profiles)
    return new


def delete_local(alias):
    """Remove an entry. Returns True if removed, False if alias was
    not present."""
    profiles = load_local()
    if alias not in profiles:
        return False
    del profiles[alias]
    save_local(profiles)
    return True


def piggy_aliases():
    """Return (set_of_aliases, default_alias_or_empty).

    Best-effort: returns empty values when owa-piggy is not on PATH,
    times out, or returns invalid JSON. Callers use this for collision
    detection and listings; they never block on it.
    """
    try:
        profiles = core_auth.get_profiles(tool_name='owa-cal')
    except OwaError:
        return set(), ''
    aliases = {profile.alias for profile in profiles}
    default = next((profile.alias for profile in profiles if profile.default), '')
    return aliases, default
