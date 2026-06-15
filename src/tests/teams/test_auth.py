"""Auth wiring tests for owa-teams - the two-door token setup. No network."""
import types

from owa_core import errors
from owa_teams import auth as auth_mod


def _fake_token(access='tok'):
    return types.SimpleNamespace(access_token=access)


def test_graph_setup_returns_graph_base(monkeypatch):
    seen = {}

    def fake_get(config, *, tool_name, audience, debug=False):
        seen.update(tool_name=tool_name, audience=audience)
        return _fake_token()

    monkeypatch.setattr(auth_mod._core, 'get_token_for_config', fake_get)
    token, base = auth_mod.graph_setup({})
    assert token == 'tok'
    assert base == auth_mod.GRAPH_BASE
    assert seen == {'tool_name': 'owa-teams', 'audience': 'graph'}


def test_chatsvc_setup_uses_ic3_and_region(monkeypatch):
    seen = {}

    def fake_get(config, *, tool_name, audience, debug=False):
        seen['audience'] = audience
        return _fake_token('ic3tok')

    monkeypatch.setattr(auth_mod._core, 'get_token_for_config', fake_get)
    token, base = auth_mod.chatsvc_setup({'teams_region': 'AMER'})
    assert token == 'ic3tok'
    assert seen['audience'] == 'ic3'
    assert base == 'https://teams.microsoft.com/api/chatsvc/amer/v1'


def test_chatsvc_setup_defaults_to_emea(monkeypatch):
    monkeypatch.setattr(auth_mod._core, 'get_token_for_config',
                        lambda config, **k: _fake_token())
    _token, base = auth_mod.chatsvc_setup({})
    assert base.endswith('/chatsvc/emea/v1')


def test_chatsvc_setup_region_override_wins_over_config(monkeypatch):
    monkeypatch.setattr(auth_mod._core, 'get_token_for_config',
                        lambda config, **k: _fake_token())
    _token, base = auth_mod.chatsvc_setup({'teams_region': 'emea'}, region='  APAC ')
    assert base.endswith('/chatsvc/apac/v1')


def test_chatsvc_setup_empty_region_override_falls_back_to_config(monkeypatch):
    monkeypatch.setattr(auth_mod._core, 'get_token_for_config',
                        lambda config, **k: _fake_token())
    _token, base = auth_mod.chatsvc_setup({'teams_region': 'amer'}, region='')
    assert base.endswith('/chatsvc/amer/v1')


def test_resolve_region():
    assert auth_mod.resolve_region({}) == 'emea'
    assert auth_mod.resolve_region({'teams_region': '  APAC '}) == 'apac'
    assert auth_mod.resolve_region({'teams_region': ''}) == 'emea'


def test_do_graph_refresh_happy(monkeypatch):
    monkeypatch.setattr(auth_mod._core, 'get_token_for_config', lambda config, **k: _fake_token('x'))
    assert auth_mod.do_graph_refresh({}) == 'x'


def test_do_graph_refresh_failure_emits_and_returns_none(monkeypatch, capsys):
    def boom(config, **k):
        raise errors.AuthExpiredError('broker down', remediation='run owa-piggy setup')

    monkeypatch.setattr(auth_mod._core, 'get_token_for_config', boom)
    assert auth_mod.do_graph_refresh({}) is None
    err = capsys.readouterr().err
    assert 'broker down' in err
