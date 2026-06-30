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
from owa_core.registry import CONSUMER_TOOLS

# owa-piggy (the auth broker) plus every consumer CLI, derived from the
# canonical registry so a newly added tool is probed automatically.
SIBLINGS = ('owa-piggy',) + CONSUMER_TOOLS

# Default timeout (seconds) for doctor's own subprocess probes
# (`<cmd> --version`, broker reachability). The `--timeout` flag overrides it.
DEFAULT_TIMEOUT = 5

# Audiences whose token-mint surface --coverage probes per profile. Kept small
# and stdlib-derived; mirrors the audiences the suite actually exchanges for.
COVERAGE_AUDIENCES = ('graph', 'outlook')


def _which(cmd):
    return shutil.which(cmd)


def _version_of(cmd, timeout=DEFAULT_TIMEOUT):
    """Run `<cmd> --version` and return the parsed version string,
    or None if the tool is missing or doesn't print one."""
    path = _which(cmd)
    if not path:
        return None
    try:
        proc = subprocess.run(
            [cmd, '--version'],
            capture_output=True, text=True, check=False, timeout=timeout,
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


def probe_piggy(timeout=DEFAULT_TIMEOUT):
    """Return {installed, reachable, version, path}.

    `installed` means owa-piggy is on PATH; `reachable` means it actually
    answered `--version` within the timeout (a broker that is present but
    wedged is installed-but-unreachable).
    """
    path = _which('owa-piggy')
    if not path:
        return {'installed': False, 'reachable': False, 'version': None, 'path': None}
    version = _version_of('owa-piggy', timeout=timeout)
    return {
        'installed': True,
        'reachable': version is not None,
        'version': version,
        'path': path,
    }


def probe_siblings(timeout=DEFAULT_TIMEOUT):
    """Return one dict per known sibling CLI."""
    out = []
    for name in SIBLINGS:
        if name == 'owa-piggy':
            continue
        path = _which(name)
        out.append({
            'name': name,
            'installed': path is not None,
            'version': _version_of(name, timeout=timeout) if path else None,
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
        'audience_mismatch': False,
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
    finding['audience_mismatch'] = _audience_mismatch(audience, finding['token_audience'])
    return finding


# Maps the short audience names the broker accepts to a substring that must
# appear in the resource URI of the minted token's `aud` claim. A token whose
# audience does not contain the expected marker means the broker handed back a
# token for the wrong resource than what a command for that audience needs.
_AUDIENCE_MARKERS = {
    'graph': 'graph.microsoft.com',
    'outlook': 'outlook.office',
}


def _audience_mismatch(requested, token_audience):
    """True when the minted token's `aud` does not match the requested one."""
    marker = _AUDIENCE_MARKERS.get(requested)
    if not marker or not token_audience:
        return False
    return marker not in token_audience


def probe_profile_coverage(alias, audiences=COVERAGE_AUDIENCES):
    """Report which audiences/scopes a profile can actually obtain a token for.

    Reuses probe_profile_token (the same broker token-mint surface the health
    check uses) once per audience. Returns {audience: bool obtainable}.
    """
    return {
        audience: probe_profile_token(alias, audience=audience)['token_ok']
        for audience in audiences
    }


def classify_finding(finding):
    """Bucket a profile finding into ok / warn / fail.

    - fail: token_ok is False
    - warn: token_ok but minutes_remaining is < 10 (about to expire), or the
            minted token's audience does not match the requested one
    - ok:   everything else
    """
    if not finding.get('token_ok'):
        return 'fail'
    mins = finding.get('minutes_remaining')
    if isinstance(mins, int) and mins < 10:
        return 'warn'
    if finding.get('audience_mismatch'):
        return 'warn'
    return 'ok'
