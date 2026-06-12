"""Confirmation prompts and pretty-print paths for owa-ado."""
import pytest

from owa_ado import api as api_mod
from owa_ado import auth as auth_mod
from owa_ado import cli as cli_mod
from owa_core import tty as tty_mod
from owa_core.errors import UsageError


@pytest.fixture(autouse=True)
def _stub_auth(monkeypatch):
    monkeypatch.setattr(auth_mod, 'setup_auth', lambda config, debug=False: 'tok')


def _base(argv):
    return cli_mod.main(['--org', 'O', '--project', 'P', *argv])


# --- confirmation gate --------------------------------------------------

def test_wi_create_prompts_and_proceeds_on_yes(monkeypatch, tmp_config, clean_env):
    monkeypatch.setattr(tty_mod, 'require_confirm_or_tty', lambda *, action: None)
    monkeypatch.setattr(tty_mod, 'confirm', lambda *a, **k: True)
    called = {}
    monkeypatch.setattr(api_mod, 'json_patch',
                        lambda *a, **k: called.update(hit=True) or {'id': 1, 'fields': {}})
    rc = _base(['wi-create', '--type', 'Task', '--title', 'x'])
    assert rc == 0
    assert called.get('hit')


def test_wi_create_aborts_on_no(monkeypatch, tmp_config, clean_env):
    monkeypatch.setattr(tty_mod, 'require_confirm_or_tty', lambda *, action: None)
    monkeypatch.setattr(tty_mod, 'confirm', lambda *a, **k: False)
    monkeypatch.setattr(api_mod, 'json_patch',
                        lambda *a, **k: pytest.fail('must not write on abort'))
    rc = _base(['wi-create', '--type', 'Task', '--title', 'x'])
    assert rc == 1


def test_wi_create_non_tty_is_usage_error(monkeypatch, tmp_config, clean_env):
    def boom(*, action):
        raise UsageError('not a tty; pass --confirm')

    monkeypatch.setattr(tty_mod, 'require_confirm_or_tty', boom)
    rc = _base(['wi-create', '--type', 'Task', '--title', 'x'])
    assert rc == 2


def test_wi_update_prompts_and_proceeds(monkeypatch, tmp_config, clean_env):
    monkeypatch.setattr(tty_mod, 'require_confirm_or_tty', lambda *, action: None)
    monkeypatch.setattr(tty_mod, 'confirm', lambda *a, **k: True)
    called = {}
    monkeypatch.setattr(api_mod, 'json_patch',
                        lambda *a, **k: called.update(hit=True) or {'id': 5, 'fields': {}})
    rc = _base(['wi-update', '5', '--state', 'Active'])
    assert rc == 0
    assert called.get('hit')


def test_wi_update_aborts_on_no(monkeypatch, tmp_config, clean_env):
    monkeypatch.setattr(tty_mod, 'require_confirm_or_tty', lambda *, action: None)
    monkeypatch.setattr(tty_mod, 'confirm', lambda *a, **k: False)
    rc = _base(['wi-update', '5', '--state', 'Active'])
    assert rc == 1


# --- pretty-print paths -------------------------------------------------

def test_wi_show_pretty(monkeypatch, tmp_config, clean_env, capsys):
    monkeypatch.setattr(api_mod, 'ado_request',
                        lambda *a, **k: {'id': 7, 'fields': {'System.Title': 'T',
                                                             'System.WorkItemType': 'Bug',
                                                             'System.State': 'Active'}})
    assert _base(['wi', '7', '--pretty']) == 0
    assert '#7 T [Bug]' in capsys.readouterr().out


def test_wi_list_pretty(monkeypatch, tmp_config, clean_env, capsys):
    def fake_request(method, base, endpoint, token, **kwargs):
        if endpoint.endswith('/wiql'):
            return {'workItems': [{'id': 1}]}
        return {'value': [{'id': 1, 'fields': {'System.Title': 'A', 'System.State': 'New',
                                               'System.WorkItemType': 'Task'}}]}

    monkeypatch.setattr(api_mod, 'ado_request', fake_request)
    assert _base(['wi', '--mine', '--pretty']) == 0
    out = capsys.readouterr().out
    assert 'id' in out and 'title' in out


def test_prs_show_pretty(monkeypatch, tmp_config, clean_env, capsys):
    monkeypatch.setattr(api_mod, 'ado_request',
                        lambda *a, **k: {'pullRequestId': 9, 'title': 'PR', 'status': 'active'})
    assert _base(['prs', '9', '--pretty']) == 0
    assert '!9 PR [active]' in capsys.readouterr().out


def test_sprints_pretty(monkeypatch, tmp_config, clean_env, capsys):
    monkeypatch.setattr(api_mod, 'ado_request',
                        lambda *a, **k: {'value': [{'name': 'CD 1', 'path': 'P\\CD 1',
                                                    'attributes': {'timeFrame': 'current'}}]})
    assert _base(['sprints', '--pretty']) == 0
    assert 'CD 1' in capsys.readouterr().out


def test_runs_pretty(monkeypatch, tmp_config, clean_env, capsys):
    monkeypatch.setattr(api_mod, 'ado_request',
                        lambda *a, **k: {'value': [{'id': 1, 'buildNumber': '1',
                                                    'status': 'completed', 'result': 'succeeded',
                                                    'definition': {'name': 'CI'},
                                                    'sourceBranch': 'refs/heads/main'}]})
    assert _base(['runs', '--pretty']) == 0
    assert 'CI' in capsys.readouterr().out


def test_pipelines_pretty(monkeypatch, tmp_config, clean_env, capsys):
    monkeypatch.setattr(api_mod, 'ado_request',
                        lambda *a, **k: {'value': [{'id': 8, 'name': 'Deploy', 'folder': '\\'}]})
    assert _base(['pipelines', '--pretty']) == 0
    assert 'Deploy' in capsys.readouterr().out


def test_prs_list_pretty(monkeypatch, tmp_config, clean_env, capsys):
    monkeypatch.setattr(api_mod, 'ado_request',
                        lambda *a, **k: {'value': [{'pullRequestId': 1, 'title': 'x',
                                                    'status': 'active', 'repository': {'name': 'R'},
                                                    'createdBy': {'displayName': 'Kim'}}]})
    assert _base(['prs', '--pretty']) == 0
    assert 'status' in capsys.readouterr().out


# --- refresh failure path ----------------------------------------------

def test_refresh_unreachable_org(monkeypatch, tmp_config, clean_env):
    monkeypatch.setattr(auth_mod, 'do_token_refresh', lambda c, debug=False: 'tok')
    monkeypatch.setattr(api_mod, 'ado_request', lambda *a, **k: None)
    assert cli_mod.main(['--org', 'O', 'refresh']) == 1
