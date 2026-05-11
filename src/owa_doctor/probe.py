"""Health probes.

Each probe is a pure-ish function returning a JSON-serialisable dict.
The CLI composes them into a full report. No probe ever exits the
process - failure cases produce structured findings instead.

We call sibling CLIs for version checks. Token and profile broker calls
go through owa_core.auth so the JSON contract and redaction behavior
stay centralized.
"""
import re
import shutil
import subprocess

from owa_core import auth as core_auth
from owa_core.errors import OwaError
from owa_core.jwt import decode_token_audience, token_minutes_remaining

SIBLINGS = ('owa-piggy', 'owa-cal', 'owa-mail', 'owa-graph',
            'owa-people', 'owa-sched', 'owa-drive', 'owa-doctor')


def _which(cmd):
    return shutil.which(cmd)


def _version_of(cmd):
    """Run `<cmd> --version` and return the parsed version string,
    or None if the tool is missing or doesn't print one."""
    path = _which(cmd)
    if not path:
        return None
    try:
        proc = subprocess.run(
            [cmd, '--version'],
            capture_output=True, text=True, check=False, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    raw = (proc.stdout or proc.stderr).strip()
    # argparse default form is "<prog> X.Y.Z"; some tools print just
    # the version. Take the first dotted-numeric token we find.
    for tok in raw.split():
        if re.fullmatch(r'\d+\.\d+\.\d+([.-].*)?', tok):
            return tok
    return None


def probe_piggy():
    """Return {installed, version, path}."""
    path = _which('owa-piggy')
    if not path:
        return {'installed': False, 'version': None, 'path': None}
    return {
        'installed': True,
        'version': _version_of('owa-piggy'),
        'path': path,
    }


def probe_siblings():
    """Return one dict per known sibling CLI."""
    out = []
    for name in SIBLINGS:
        if name == 'owa-piggy':
            continue
        path = _which(name)
        out.append({
            'name': name,
            'installed': path is not None,
            'version': _version_of(name) if path else None,
            'path': path,
        })
    return out


def list_piggy_profiles():
    """Return (aliases_list, default_alias_or_None).

    This uses the broker JSON profile contract and degrades to an empty
    list when the broker is unavailable.
    """
    try:
        profiles = core_auth.get_profiles(tool_name='owa-doctor')
    except OwaError:
        return [], None
    aliases = [profile.alias for profile in profiles]
    default = next((profile.alias for profile in profiles if profile.default), None)
    return aliases, default


def probe_profile_token(alias, audience='graph'):
    """Try to mint a token for one profile and report on it.

    Returns a structured finding. We deliberately request `--audience
    graph` because that's the one most siblings need; the user can
    override on the CLI.
    """
    finding = {
        'alias': alias,
        'audience': audience,
        'token_ok': False,
        'minutes_remaining': None,
        'token_audience': None,
        'error': None,
    }
    try:
        token = core_auth.get_token(
            tool_name='owa-doctor',
            audience=audience,
            profile=alias,
        )
    except OwaError as error:
        finding['error'] = error.message
        return finding
    finding['token_ok'] = True
    access = token.access_token
    finding['minutes_remaining'] = token_minutes_remaining(access)
    finding['token_audience'] = decode_token_audience(access)
    return finding


def classify_finding(finding):
    """Bucket a profile finding into ok / warn / fail.

    - fail: token_ok is False
    - warn: token_ok but minutes_remaining is < 10 (about to expire)
    - ok:   everything else
    """
    if not finding.get('token_ok'):
        return 'fail'
    mins = finding.get('minutes_remaining')
    if isinstance(mins, int) and mins < 10:
        return 'warn'
    return 'ok'
