"""Coverage for owa-ado help/version/config/refresh and flag parsing."""
import json

import pytest

from owa_ado import api as api_mod
from owa_ado import auth as auth_mod
from owa_ado import cli as cli_mod


@pytest.fixture(autouse=True)
def _stub_auth(monkeypatch):
    monkeypatch.setattr(auth_mod, 'setup_auth', lambda config, debug=False: 'tok')


# --- help / version / schema --------------------------------------------

def test_help_command(capsys):
    assert cli_mod.main(['help']) == 0
    assert 'Usage: owa-ado' in capsys.readouterr().out


def test_version_command(capsys):
    assert cli_mod.main(['--version']) == 0
    assert capsys.readouterr().out.strip().startswith('owa-ado ')


def test_subcommand_help(capsys):
    rc = cli_mod.main(['wi', '--help'])
    assert rc == 0
    out = capsys.readouterr().out
    assert 'wi' in out


# --- config -------------------------------------------------------------

def test_config_writes_and_reads_back(tmp_config, clean_env, capsys):
    rc = cli_mod.main(['config', '--org', 'Org', '--project', 'Proj',
                       '--profile', 'work'])
    assert rc == 0
    assert tmp_config.read_text().count('=') >= 3

    rc = cli_mod.main(['config'])
    assert rc == 0
    err = capsys.readouterr().err
    assert 'ado_org=Org' in err
    assert 'ado_project=Proj' in err


def test_config_unknown_flag_is_usage_error(tmp_config, clean_env):
    assert cli_mod.main(['config', '--bogus', 'x']) == 2


# --- refresh ------------------------------------------------------------

def test_refresh_ok(monkeypatch, tmp_config, clean_env, capsys):
    monkeypatch.setattr(auth_mod, 'do_token_refresh', lambda c, debug=False: 'tok')
    monkeypatch.setattr(api_mod, 'ado_request', lambda *a, **k: {'count': 2})
    rc = cli_mod.main(['--org', 'Org', 'refresh'])
    assert rc == 0
    assert 'Authenticated against Org' in capsys.readouterr().err


def test_refresh_failed_token(monkeypatch, tmp_config, clean_env):
    monkeypatch.setattr(auth_mod, 'do_token_refresh', lambda c, debug=False: None)
    assert cli_mod.main(['--org', 'Org', 'refresh']) == 1


# --- global flag parsing ------------------------------------------------

def test_short_org_project_flags(monkeypatch, tmp_config, clean_env, capsys):
    seen = {}

    def fake_request(method, base, endpoint, token, **kwargs):
        seen['base'] = base
        seen['endpoint'] = endpoint
        return {'value': []}

    monkeypatch.setattr(api_mod, 'ado_request', fake_request)
    rc = cli_mod.main(['-o', 'OrgX', '-P', 'ProjX', 'repos'])
    assert rc == 0
    assert seen['base'].endswith('/OrgX')
    assert seen['endpoint'] == 'ProjX/_apis/git/repositories'


def test_env_supplies_org_and_project(monkeypatch, tmp_config, clean_env):
    monkeypatch.setenv('OWA_ADO_ORG', 'EnvOrg')
    monkeypatch.setenv('OWA_ADO_PROJECT', 'EnvProj')
    seen = {}
    monkeypatch.setattr(api_mod, 'ado_request',
                        lambda m, base, ep, t, **k: seen.update(base=base) or {'value': []})
    assert cli_mod.main(['repos']) == 0
    assert seen['base'].endswith('/EnvOrg')


def test_debug_flag_enables_verbose(monkeypatch, tmp_config, clean_env, capsys):
    monkeypatch.setattr(api_mod, 'ado_request', lambda *a, **k: {'value': []})
    rc = cli_mod.main(['--org', 'O', '--project', 'P', '--debug', 'repos'])
    assert rc == 0
    assert 'verbose logging enabled' in capsys.readouterr().err


# --- command variants ---------------------------------------------------

def test_wi_raw_query_skips_builder(monkeypatch, tmp_config, clean_env):
    calls = []

    def fake_request(method, base, endpoint, token, **kwargs):
        calls.append((endpoint, kwargs.get('body')))
        if endpoint.endswith('/wiql'):
            return {'workItems': []}
        return {'value': []}

    monkeypatch.setattr(api_mod, 'ado_request', fake_request)
    rc = cli_mod.main(['--org', 'O', '--project', 'P', 'wi',
                       '--query', 'SELECT [System.Id] FROM workitems'])
    assert rc == 0
    assert calls[0][1] == {'query': 'SELECT [System.Id] FROM workitems'}


def test_wi_create_with_parent_adds_relation(monkeypatch, tmp_config, clean_env):
    seen = {}

    def fake_patch(method, base, endpoint, token, *, operations, **kwargs):
        seen['ops'] = operations
        return {'id': 1, 'fields': {}}

    monkeypatch.setattr(api_mod, 'json_patch', fake_patch)
    rc = cli_mod.main(['--org', 'O', '--project', 'P', 'wi-create',
                       '--type', 'Task', '--title', 'child',
                       '--field', 'Microsoft.VSTS.Common.Priority=1',
                       '--parent', '42', '--confirm'])
    assert rc == 0
    rel = [o for o in seen['ops'] if o['path'] == '/relations/-']
    assert rel and rel[0]['value']['url'].endswith('/_apis/wit/workItems/42')
    # A dotted field path is used verbatim (not namespaced under System.).
    pri = [o for o in seen['ops'] if o['path'] == '/fields/Microsoft.VSTS.Common.Priority']
    assert pri and pri[0]['value'] == '1'


def test_wi_create_bad_field_is_usage_error(tmp_config, clean_env):
    rc = cli_mod.main(['--org', 'O', '--project', 'P', 'wi-create',
                       '--type', 'Task', '--title', 'x',
                       '--field', 'noequalshere', '--confirm'])
    assert rc == 2


def test_prs_no_filters_defaults(monkeypatch, tmp_config, clean_env):
    seen = {}
    monkeypatch.setattr(api_mod, 'ado_request',
                        lambda m, base, ep, t, **k: seen.update(query=k.get('query'), ep=ep) or {'value': []})
    assert cli_mod.main(['--org', 'O', '--project', 'P', 'prs']) == 0
    assert seen['ep'] == 'P/_apis/git/pullrequests'
    assert seen['query'] == {'$top': 50}


def test_sprints_custom_team(monkeypatch, tmp_config, clean_env):
    seen = {}
    monkeypatch.setattr(api_mod, 'ado_request',
                        lambda m, base, ep, t, **k: seen.update(ep=ep) or {'value': []})
    assert cli_mod.main(['--org', 'O', '--project', 'P', 'sprints',
                         '--team', 'Custom Team']) == 0
    assert seen['ep'] == 'P/Custom Team/_apis/work/teamsettings/iterations'


def test_repos_all_paginates(monkeypatch, tmp_config, clean_env):
    seen = {}
    monkeypatch.setattr(api_mod, 'ado_paginate',
                        lambda base, ep, t, **k: seen.update(ep=ep) or [])
    assert cli_mod.main(['--org', 'O', '--project', 'P', 'repos', '--all']) == 0
    assert seen['ep'] == 'P/_apis/git/repositories'


def test_pipelines_all_paginates(monkeypatch, tmp_config, clean_env):
    seen = {}
    monkeypatch.setattr(api_mod, 'ado_paginate',
                        lambda base, ep, t, **k: seen.update(ep=ep) or [])
    assert cli_mod.main(['--org', 'O', '--project', 'P', 'pipelines', '--all']) == 0
    assert seen['ep'] == 'P/_apis/pipelines'


def test_runs_without_pipeline(monkeypatch, tmp_config, clean_env):
    seen = {}
    monkeypatch.setattr(api_mod, 'ado_request',
                        lambda m, base, ep, t, **k: seen.update(query=k.get('query')) or {'value': []})
    assert cli_mod.main(['--org', 'O', '--project', 'P', 'runs']) == 0
    assert seen['query'] == {'$top': 20}


def test_unknown_flag_in_command_is_usage_error(monkeypatch, tmp_config, clean_env):
    monkeypatch.setattr(api_mod, 'ado_request', lambda *a, **k: {'value': []})
    assert cli_mod.main(['--org', 'O', '--project', 'P', 'repos', '--nope']) == 2


def test_bad_top_value_is_usage_error(tmp_config, clean_env):
    assert cli_mod.main(['--org', 'O', '--project', 'P', 'wi', '--top', 'abc']) == 2


def test_pretty_path_renders_table(monkeypatch, tmp_config, clean_env, capsys):
    monkeypatch.setattr(api_mod, 'ado_request',
                        lambda *a, **k: {'value': [{'id': 'p', 'name': 'NOCOS',
                                                    'state': 'wellFormed',
                                                    'visibility': 'private'}]})
    assert cli_mod.main(['--org', 'O', 'projects', '--pretty']) == 0
    out = capsys.readouterr().out
    assert 'NOCOS' in out and 'name' in out
