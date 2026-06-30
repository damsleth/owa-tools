"""Unit tests for probe functions. Stub subprocess so nothing real runs."""
import subprocess

from owa_core.auth import BrokerProfile, BrokerToken
from owa_core.errors import AuthExpiredError
from owa_doctor import probe as probe_mod


class _FakeProc:
    def __init__(self, returncode=0, stdout='', stderr=''):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_probe_piggy_missing(monkeypatch):
    monkeypatch.setattr(probe_mod, '_which', lambda c: None)
    out = probe_mod.probe_piggy()
    assert out == {'installed': False, 'reachable': False, 'version': None, 'path': None}


def test_probe_piggy_present(monkeypatch):
    monkeypatch.setattr(probe_mod, '_which', lambda c: '/usr/bin/owa-piggy')
    monkeypatch.setattr(
        subprocess, 'run',
        lambda *a, **kw: _FakeProc(stdout='owa-piggy 0.7.1\n'),
    )
    out = probe_mod.probe_piggy()
    assert out['installed'] is True
    assert out['version'] == '0.7.1'
    assert out['path'] == '/usr/bin/owa-piggy'


def test_list_piggy_profiles_parses_default_marker(monkeypatch):
    monkeypatch.setattr(probe_mod.core_auth, 'get_profiles', lambda **kwargs: [
        BrokerProfile('brkh', default=False, registered=True, has_config=True),
        BrokerProfile('acme', default=False, registered=True, has_config=True),
        BrokerProfile('globex', default=True, registered=True, has_config=True),
    ])
    aliases, default = probe_mod.list_piggy_profiles()
    assert aliases == ['brkh', 'acme', 'globex']
    assert default == 'globex'


def test_list_piggy_profiles_no_piggy(monkeypatch):
    def _raise(**kwargs):
        raise AuthExpiredError('owa-piggy not found')

    monkeypatch.setattr(probe_mod.core_auth, 'get_profiles', _raise)
    aliases, default = probe_mod.list_piggy_profiles()
    assert aliases == []
    assert default is None


def test_probe_profile_token_failure_captures_aadsts(monkeypatch):
    def _raise(**kwargs):
        raise AuthExpiredError('ERROR: invalid_grant: AADSTS70043: refresh token expired')

    monkeypatch.setattr(probe_mod.core_auth, 'get_token', _raise)
    finding = probe_mod.probe_profile_token('acme')
    assert finding['token_ok'] is False
    assert 'AADSTS70043' in finding['error']
    assert finding['minutes_remaining'] is None


def test_probe_profile_token_ok(monkeypatch):
    """A valid JWT comes back from owa-piggy; we decode minutes/aud."""
    import base64
    import json as _json
    import time

    payload = {
        'exp': int(time.time()) + 3600,
        'aud': 'https://graph.microsoft.com',
    }

    def b64(b):
        return base64.urlsafe_b64encode(b).rstrip(b'=').decode('ascii')

    fake_jwt = '.'.join((
        b64(b'{"alg":"RS256"}'),
        b64(_json.dumps(payload).encode()),
        'sig',
    ))

    monkeypatch.setattr(
        probe_mod.core_auth,
        'get_token',
        lambda **kwargs: BrokerToken(access_token=fake_jwt, audience='graph', profile='globex'),
    )
    finding = probe_mod.probe_profile_token('globex')
    assert finding['token_ok'] is True
    assert isinstance(finding['minutes_remaining'], int)
    assert finding['minutes_remaining'] >= 59
    assert finding['token_audience'] == 'https://graph.microsoft.com'


def test_classify_finding():
    assert probe_mod.classify_finding({'token_ok': False}) == 'fail'
    assert probe_mod.classify_finding(
        {'token_ok': True, 'minutes_remaining': 5}
    ) == 'warn'
    assert probe_mod.classify_finding(
        {'token_ok': True, 'minutes_remaining': 60}
    ) == 'ok'
    assert probe_mod.classify_finding(
        {'token_ok': True, 'minutes_remaining': None}
    ) == 'ok'


def test_probe_piggy_unreachable(monkeypatch):
    """Broker on PATH but --version times out -> installed but not reachable."""
    monkeypatch.setattr(probe_mod, '_which', lambda c: '/usr/bin/owa-piggy')

    def _timeout(*a, **kw):
        raise subprocess.TimeoutExpired(cmd='owa-piggy', timeout=kw.get('timeout'))

    monkeypatch.setattr(subprocess, 'run', _timeout)
    out = probe_mod.probe_piggy(timeout=1)
    assert out['installed'] is True
    assert out['reachable'] is False
    assert out['version'] is None


def test_version_of_threads_timeout(monkeypatch):
    seen = {}

    def _run(argv, **kw):
        seen['timeout'] = kw.get('timeout')
        return _FakeProc(stdout='owa-cal 1.2.3\n')

    monkeypatch.setattr(probe_mod, '_which', lambda c: '/usr/bin/owa-cal')
    monkeypatch.setattr(subprocess, 'run', _run)
    assert probe_mod._version_of('owa-cal', timeout=9) == '1.2.3'
    assert seen['timeout'] == 9


def test_audience_mismatch_helper():
    # graph token for a graph request -> no mismatch
    assert probe_mod._audience_mismatch('graph', 'https://graph.microsoft.com') is False
    # graph requested but an outlook token came back -> mismatch
    assert probe_mod._audience_mismatch('graph', 'https://outlook.office.com') is True
    # unknown audience or missing token audience -> never flagged
    assert probe_mod._audience_mismatch('weird', 'whatever') is False
    assert probe_mod._audience_mismatch('graph', None) is False


def test_probe_profile_token_flags_audience_mismatch(monkeypatch):
    import base64
    import json as _json
    import time

    payload = {'exp': int(time.time()) + 3600, 'aud': 'https://outlook.office.com'}

    def b64(b):
        return base64.urlsafe_b64encode(b).rstrip(b'=').decode('ascii')

    fake_jwt = '.'.join((b64(b'{"alg":"RS256"}'), b64(_json.dumps(payload).encode()), 'sig'))
    monkeypatch.setattr(
        probe_mod.core_auth, 'get_token',
        lambda **kwargs: BrokerToken(access_token=fake_jwt, audience='graph', profile='globex'),
    )
    finding = probe_mod.probe_profile_token('globex', audience='graph')
    assert finding['token_ok'] is True
    assert finding['audience_mismatch'] is True
    assert probe_mod.classify_finding(finding) == 'warn'


def test_probe_profile_coverage(monkeypatch):
    def fake_token(alias, audience='graph'):
        return {'token_ok': audience == 'graph'}

    monkeypatch.setattr(probe_mod, 'probe_profile_token', fake_token)
    cov = probe_mod.probe_profile_coverage('globex', audiences=('graph', 'outlook'))
    assert cov == {'graph': True, 'outlook': False}
