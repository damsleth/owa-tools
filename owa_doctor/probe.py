"""Health probes.

Each probe is a pure-ish function returning a JSON-serialisable dict.
The CLI composes them into a full report. No probe ever exits the
process - failure cases produce structured findings instead.

We talk to owa-piggy as a sibling POSIX util (subprocess + parse),
not as a Python import. owa-piggy versions independently and may not
even be in our import path.
"""
import json
import re
import shutil
import subprocess

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
    """Run `owa-piggy profiles` and parse the alias listing.

    The human output is one alias per line, with a leading `*` marker
    on the default. Returns (aliases_list, default_alias_or_None).
    """
    if not _which('owa-piggy'):
        return [], None
    try:
        proc = subprocess.run(
            ['owa-piggy', 'profiles'],
            capture_output=True, text=True, check=False, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return [], None
    if proc.returncode != 0:
        return [], None
    aliases = []
    default = None
    for line in proc.stdout.splitlines():
        s = line.strip()
        if not s:
            continue
        is_default = s.startswith('*')
        alias = s.lstrip('* ').strip()
        if not alias or ' ' in alias:
            continue
        aliases.append(alias)
        if is_default:
            default = alias
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
    if not _which('owa-piggy'):
        finding['error'] = 'owa-piggy not on PATH'
        return finding
    argv = ['owa-piggy', 'token', '--audience', audience, '--json',
            '--profile', alias]
    try:
        proc = subprocess.run(
            argv, capture_output=True, text=True, check=False, timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        finding['error'] = f'owa-piggy invocation failed: {exc}'
        return finding
    if proc.returncode != 0:
        # Capture the most useful line of stderr - typically AADSTS...
        err = (proc.stderr or '').strip().splitlines()
        finding['error'] = err[-1] if err else f'exit {proc.returncode}'
        return finding
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        finding['error'] = 'owa-piggy returned non-JSON'
        return finding
    access = payload.get('access_token')
    if not access:
        finding['error'] = 'no access_token in piggy response'
        return finding
    finding['token_ok'] = True
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
