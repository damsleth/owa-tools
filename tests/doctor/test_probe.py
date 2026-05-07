"""Unit tests for probe functions. Stub subprocess so nothing real runs."""
import subprocess

from owa_doctor import probe as probe_mod


class _FakeProc:
    def __init__(self, returncode=0, stdout='', stderr=''):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_probe_piggy_missing(monkeypatch):
    monkeypatch.setattr(probe_mod, '_which', lambda c: None)
    out = probe_mod.probe_piggy()
    assert out == {'installed': False, 'version': None, 'path': None}


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
    monkeypatch.setattr(probe_mod, '_which', lambda c: '/usr/bin/owa-piggy')
    monkeypatch.setattr(
        subprocess, 'run',
        lambda *a, **kw: _FakeProc(stdout='   brkh\n   crayon\n * swon\n'),
    )
    aliases, default = probe_mod.list_piggy_profiles()
    assert aliases == ['brkh', 'crayon', 'swon']
    assert default == 'swon'


def test_list_piggy_profiles_no_piggy(monkeypatch):
    monkeypatch.setattr(probe_mod, '_which', lambda c: None)
    aliases, default = probe_mod.list_piggy_profiles()
    assert aliases == []
    assert default is None


def test_probe_profile_token_failure_captures_aadsts(monkeypatch):
    monkeypatch.setattr(probe_mod, '_which', lambda c: '/usr/bin/owa-piggy')
    err = (
        'WARN: refresh token rejected\n'
        'ERROR: invalid_grant: AADSTS70043: refresh token expired\n'
    )
    monkeypatch.setattr(
        subprocess, 'run',
        lambda *a, **kw: _FakeProc(returncode=1, stderr=err),
    )
    finding = probe_mod.probe_profile_token('crayon')
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

    monkeypatch.setattr(probe_mod, '_which', lambda c: '/usr/bin/owa-piggy')
    monkeypatch.setattr(
        subprocess, 'run',
        lambda *a, **kw: _FakeProc(
            stdout=_json.dumps({'access_token': fake_jwt}),
        ),
    )
    finding = probe_mod.probe_profile_token('swon')
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
