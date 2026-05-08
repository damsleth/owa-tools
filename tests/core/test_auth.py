"""Contract tests for the shared owa-piggy auth bridge."""
import json

import pytest

from owa_core import auth
from owa_core.errors import AuthExpiredError, ExitCode, InternalError


class FakeProc:
    def __init__(self, returncode=0, stdout='', stderr=''):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _patch_available(monkeypatch):
    monkeypatch.setattr(auth.shutil, 'which', lambda name: '/usr/bin/owa-piggy')


def test_get_token_returns_sanitized_payload_and_expected_argv(monkeypatch):
    _patch_available(monkeypatch)
    calls = []
    token_body = {
        'access_token': 'fake-access-token-for-tests',
        'refresh_token': 'must-not-leak',
        'expires_in': '3600',
        'expires_at': 1893456000,
        'token_type': 'Bearer',
        'scope': 'People.Read',
    }

    def fake_run(argv, *args, **kwargs):
        calls.append(argv)
        if argv == ['owa-piggy', '--version']:
            return FakeProc(stdout='owa-piggy 0.7.1\n')
        return FakeProc(stdout=json.dumps(token_body))

    monkeypatch.setattr(auth.subprocess, 'run', fake_run)
    token = auth.get_token(
        tool_name='owa-people',
        audience='graph',
        profile='work',
        scope='People.Read',
    )

    assert calls == [
        ['owa-piggy', '--version'],
        [
            'owa-piggy',
            'token',
            '--audience',
            'graph',
            '--json',
            '--scope',
            'People.Read',
            '--profile',
            'work',
        ],
    ]
    assert token.access_token == 'fake-access-token-for-tests'
    assert token.expires_in == 3600
    assert token.expires_at == 1893456000
    assert token.scope == 'People.Read'
    assert token.raw['access_token'] == 'fake-access-token-for-tests'
    assert 'refresh_token' not in token.raw


def test_get_token_for_config_uses_profile_alias(monkeypatch):
    _patch_available(monkeypatch)
    calls = []

    def fake_run(argv, *args, **kwargs):
        calls.append(argv)
        if argv == ['owa-piggy', '--version']:
            return FakeProc(stdout='owa-piggy 0.7.1\n')
        return FakeProc(stdout=json.dumps({'access_token': 'fake'}))

    monkeypatch.setattr(auth.subprocess, 'run', fake_run)
    token = auth.get_token_for_config(
        {'owa_piggy_profile': 'work'},
        tool_name='owa-people',
        audience='graph',
    )
    assert token.profile == 'work'
    assert calls[-1] == [
        'owa-piggy',
        'token',
        '--audience',
        'graph',
        '--json',
        '--profile',
        'work',
    ]


def test_missing_owa_piggy_maps_to_auth_exit(monkeypatch):
    monkeypatch.setattr(auth.shutil, 'which', lambda name: None)
    with pytest.raises(AuthExpiredError) as exc:
        auth.get_token(tool_name='owa-people', audience='graph')
    assert exc.value.exit_code == ExitCode.AUTH_EXPIRED
    assert 'owa-piggy not found' in exc.value.message


def test_old_owa_piggy_version_maps_to_auth_exit(monkeypatch):
    _patch_available(monkeypatch)

    def fake_run(argv, *args, **kwargs):
        return FakeProc(stdout='owa-piggy 0.7.0\n')

    monkeypatch.setattr(auth.subprocess, 'run', fake_run)
    with pytest.raises(AuthExpiredError) as exc:
        auth.get_token(tool_name='owa-people', audience='graph')
    assert exc.value.exit_code == ExitCode.AUTH_EXPIRED
    assert 'too old' in exc.value.message


def test_unparseable_owa_piggy_version_does_not_block(monkeypatch):
    _patch_available(monkeypatch)
    calls = []

    def fake_run(argv, *args, **kwargs):
        calls.append(argv)
        if argv == ['owa-piggy', '--version']:
            return FakeProc(stdout='not-a-version\n')
        return FakeProc(stdout=json.dumps({'access_token': 'fake'}))

    monkeypatch.setattr(auth.subprocess, 'run', fake_run)
    token = auth.get_token(tool_name='owa-people', audience='graph')
    assert token.access_token == 'fake'
    assert calls[0] == ['owa-piggy', '--version']


def test_owa_piggy_version_command_failures_map_to_auth(monkeypatch):
    _patch_available(monkeypatch)
    monkeypatch.setattr(
        auth.subprocess,
        'run',
        lambda argv, *args, **kwargs: FakeProc(returncode=2, stderr='boom'),
    )
    with pytest.raises(AuthExpiredError) as exc:
        auth.get_token(tool_name='owa-people', audience='graph')
    assert 'version failed' in exc.value.message


def test_owa_piggy_version_oserror_maps_to_auth(monkeypatch):
    _patch_available(monkeypatch)

    def fake_run(argv, *args, **kwargs):
        raise OSError('blocked')

    monkeypatch.setattr(auth.subprocess, 'run', fake_run)
    with pytest.raises(AuthExpiredError) as exc:
        auth.get_token(tool_name='owa-people', audience='graph')
    assert 'failed to run owa-piggy --version' in exc.value.message


def test_token_command_failure_uses_broker_stderr(monkeypatch):
    _patch_available(monkeypatch)

    def fake_run(argv, *args, **kwargs):
        if argv == ['owa-piggy', '--version']:
            return FakeProc(stdout='owa-piggy 0.7.1\n')
        return FakeProc(returncode=1, stderr='ERROR: profile not found')

    monkeypatch.setattr(auth.subprocess, 'run', fake_run)
    with pytest.raises(AuthExpiredError) as exc:
        auth.get_token(tool_name='owa-people', audience='graph')
    assert 'profile not found' in exc.value.message


def test_token_command_failure_redacts_broker_stderr(monkeypatch):
    _patch_available(monkeypatch)
    access_token = '.'.join([
        'eyJhbGciOiJIUzI1NiIs',
        'eyJhdWQiOiJvd2EtdG9vbHMi',
        'c2lnbmF0dXJlZm9ydGVzdHM',
    ])

    def fake_run(argv, *args, **kwargs):
        if argv == ['owa-piggy', '--version']:
            return FakeProc(stdout='owa-piggy 0.7.1\n')
        return FakeProc(returncode=1, stderr=f'ERROR: leaked {access_token}')

    monkeypatch.setattr(auth.subprocess, 'run', fake_run)
    with pytest.raises(AuthExpiredError) as exc:
        auth.get_token(tool_name='owa-people', audience='graph')
    assert access_token not in exc.value.message
    assert '[redacted-secret]' in exc.value.message


def test_non_json_token_payload_maps_to_internal(monkeypatch):
    _patch_available(monkeypatch)

    def fake_run(argv, *args, **kwargs):
        if argv == ['owa-piggy', '--version']:
            return FakeProc(stdout='owa-piggy 0.7.1\n')
        return FakeProc(stdout='not-json')

    monkeypatch.setattr(auth.subprocess, 'run', fake_run)
    with pytest.raises(InternalError) as exc:
        auth.get_token(tool_name='owa-people', audience='graph')
    assert exc.value.exit_code == ExitCode.INTERNAL
    assert 'non-JSON' in exc.value.message


def test_non_object_token_payload_maps_to_internal(monkeypatch):
    _patch_available(monkeypatch)

    def fake_run(argv, *args, **kwargs):
        if argv == ['owa-piggy', '--version']:
            return FakeProc(stdout='owa-piggy 0.7.1\n')
        return FakeProc(stdout=json.dumps(['not', 'an', 'object']))

    monkeypatch.setattr(auth.subprocess, 'run', fake_run)
    with pytest.raises(InternalError) as exc:
        auth.get_token(tool_name='owa-people', audience='graph')
    assert 'invalid token payload' in exc.value.message


def test_missing_access_token_maps_to_internal(monkeypatch):
    _patch_available(monkeypatch)

    def fake_run(argv, *args, **kwargs):
        if argv == ['owa-piggy', '--version']:
            return FakeProc(stdout='owa-piggy 0.7.1\n')
        return FakeProc(stdout=json.dumps({'token_type': 'Bearer'}))

    monkeypatch.setattr(auth.subprocess, 'run', fake_run)
    with pytest.raises(InternalError) as exc:
        auth.get_token(tool_name='owa-people', audience='graph')
    assert 'access_token' in exc.value.message


def test_token_subprocess_oserror_maps_to_auth(monkeypatch):
    _patch_available(monkeypatch)

    def fake_run(argv, *args, **kwargs):
        if argv == ['owa-piggy', '--version']:
            return FakeProc(stdout='owa-piggy 0.7.1\n')
        raise OSError('blocked')

    monkeypatch.setattr(auth.subprocess, 'run', fake_run)
    with pytest.raises(AuthExpiredError) as exc:
        auth.get_token(tool_name='owa-people', audience='graph')
    assert 'failed to run owa-piggy token' in exc.value.message


def test_invalid_numeric_token_fields_become_none(monkeypatch):
    _patch_available(monkeypatch)

    def fake_run(argv, *args, **kwargs):
        if argv == ['owa-piggy', '--version']:
            return FakeProc(stdout='owa-piggy 0.7.1\n')
        return FakeProc(stdout=json.dumps({
            'access_token': 'fake',
            'expires_in': 'not-an-int',
            'expires_at': object(),
        }, default=str))

    monkeypatch.setattr(auth.subprocess, 'run', fake_run)
    token = auth.get_token(tool_name='owa-people', audience='graph')
    assert token.expires_in is None
    assert token.expires_at is None
