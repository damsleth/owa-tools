"""owa_vids.auth: broker argv shape and the mid-download refresh lambda."""
import json
from types import SimpleNamespace

import pytest

from owa_core.errors import AuthExpiredError
from owa_vids import auth as auth_mod


def _fake_broker(calls, token='tok-123'):
    def fake_run(argv, **kwargs):
        calls.append(list(argv))
        if '--version' in argv:
            return SimpleNamespace(returncode=0, stdout='owa-piggy 9.9.9', stderr='')
        return SimpleNamespace(
            returncode=0, stdout=json.dumps({'access_token': token}), stderr='',
        )
    return fake_run


def test_get_spo_token_mints_with_spo_scope(monkeypatch):
    calls = []
    monkeypatch.setattr('owa_core.auth.shutil.which', lambda _: '/usr/local/bin/owa-piggy')
    monkeypatch.setattr('owa_core.auth.subprocess.run', _fake_broker(calls))

    token = auth_mod.get_spo_token(
        {'owa_piggy_profile': 'globex'}, 'contoso-my.sharepoint.com',
    )

    assert token == 'tok-123'
    argv = calls[-1]
    assert argv[:2] == ['owa-piggy', 'token']
    assert argv[argv.index('--audience') + 1] == 'graph'
    assert argv[argv.index('--scope') + 1] == 'https://contoso-my.sharepoint.com/.default'
    assert argv[argv.index('--profile') + 1] == 'globex'


def test_get_graph_token_has_no_scope_override(monkeypatch):
    calls = []
    monkeypatch.setattr('owa_core.auth.shutil.which', lambda _: '/usr/local/bin/owa-piggy')
    monkeypatch.setattr('owa_core.auth.subprocess.run', _fake_broker(calls))

    token = auth_mod.get_graph_token({})

    assert token == 'tok-123'
    argv = calls[-1]
    assert '--scope' not in argv
    assert argv[argv.index('--audience') + 1] == 'graph'


def test_missing_broker_raises_auth_error(monkeypatch):
    monkeypatch.setattr('owa_core.auth.shutil.which', lambda _: None)
    with pytest.raises(AuthExpiredError):
        auth_mod.get_spo_token({}, 'contoso-my.sharepoint.com')


def test_make_spo_refresh_lambda(monkeypatch):
    seen = {}

    def fake_get_token(**kwargs):
        seen.update(kwargs)
        return SimpleNamespace(access_token='fresh-token')

    monkeypatch.setattr('owa_core.auth.get_token', fake_get_token)

    refresh = auth_mod.make_spo_refresh(
        {'owa_piggy_profile': 'globex'}, 'contoso-my.sharepoint.com', debug=False,
    )

    assert refresh() == 'fresh-token'
    assert seen['tool_name'] == 'owa-vids'
    assert seen['audience'] == 'graph'
    assert seen['scope'] == 'https://contoso-my.sharepoint.com/.default'
    assert seen['profile'] == 'globex'


def test_make_spo_refresh_without_profile_passes_none(monkeypatch):
    seen = {}

    def fake_get_token(**kwargs):
        seen.update(kwargs)
        return SimpleNamespace(access_token='t')

    monkeypatch.setattr('owa_core.auth.get_token', fake_get_token)
    auth_mod.make_spo_refresh({}, 'h.sharepoint.com')()
    assert seen['profile'] is None
