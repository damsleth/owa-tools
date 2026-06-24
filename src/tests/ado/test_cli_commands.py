"""Dispatch + per-command behaviour for owa-ado.

Auth and the network layer are stubbed; these tests exercise argument
parsing, endpoint/query construction, and the JSON the commands emit.
"""
import json

import pytest

from owa_ado import api as api_mod
from owa_ado import auth as auth_mod
from owa_ado import cli as cli_mod


@pytest.fixture(autouse=True)
def _stub_auth(monkeypatch):
    monkeypatch.setattr(auth_mod, 'setup_auth', lambda config, debug=False: 'tok')


def _run(argv, tmp_config, clean_env):
    return cli_mod.main(['--org', 'Org', '--project', 'Proj', *argv])


def test_projects_emits_normalized_json(monkeypatch, tmp_config, clean_env, capsys):
    seen = {}

    def fake_request(method, base, endpoint, token, **kwargs):
        seen['endpoint'] = endpoint
        return {'value': [{'id': 'p', 'name': 'NOCOS', 'state': 'wellFormed'}]}

    monkeypatch.setattr(api_mod, 'ado_request', fake_request)
    rc = _run(['projects'], tmp_config, clean_env)
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out[0]['name'] == 'NOCOS'
    assert seen['endpoint'] == '_apis/projects'


def test_projects_all_uses_paginate(monkeypatch, tmp_config, clean_env, capsys):
    called = {}

    def fake_paginate(base, endpoint, token, **kwargs):
        called['endpoint'] = endpoint
        return [{'id': 'p', 'name': 'A'}]

    monkeypatch.setattr(api_mod, 'ado_paginate', fake_paginate)
    rc = _run(['projects', '--all'], tmp_config, clean_env)
    assert rc == 0
    assert called['endpoint'] == '_apis/projects'


def test_wi_list_builds_wiql_then_batches_fields(monkeypatch, tmp_config, clean_env, capsys):
    calls = []

    def fake_request(method, base, endpoint, token, **kwargs):
        calls.append((method, endpoint, kwargs.get('body'), kwargs.get('query')))
        if endpoint.endswith('/wiql'):
            return {'workItems': [{'id': 11}, {'id': 22}]}
        return {'value': [
            {'id': 11, 'fields': {'System.Title': 'A', 'System.State': 'Active'}},
            {'id': 22, 'fields': {'System.Title': 'B', 'System.State': 'New'}},
        ]}

    monkeypatch.setattr(api_mod, 'ado_request', fake_request)
    rc = _run(['wi', '--mine', '--top', '5'], tmp_config, clean_env)
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert [w['id'] for w in out] == [11, 22]
    # First call posts WIQL with a $top query param; second batch-gets ids.
    assert calls[0][0] == 'POST' and calls[0][1].endswith('/wiql')
    assert calls[0][3] == {'$top': 5}
    assert calls[1][1] == '_apis/wit/workitems'
    assert calls[1][3]['ids'] == '11,22'


def test_wi_show_single_by_id(monkeypatch, tmp_config, clean_env, capsys):
    def fake_request(method, base, endpoint, token, **kwargs):
        assert endpoint == '_apis/wit/workitems/777'
        return {'id': 777, 'fields': {'System.Title': 'One', 'System.WorkItemType': 'Bug'}}

    monkeypatch.setattr(api_mod, 'ado_request', fake_request)
    rc = _run(['wi', '777'], tmp_config, clean_env)
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out['id'] == 777 and out['type'] == 'Bug'


def test_wi_empty_result_emits_empty_list(monkeypatch, tmp_config, clean_env, capsys):
    def fake_request(method, base, endpoint, token, **kwargs):
        return {'workItems': []}

    monkeypatch.setattr(api_mod, 'ado_request', fake_request)
    rc = _run(['wi', '--mine'], tmp_config, clean_env)
    assert rc == 0
    assert json.loads(capsys.readouterr().out) == []


def test_wi_create_builds_json_patch_ops(monkeypatch, tmp_config, clean_env, capsys):
    seen = {}

    def fake_patch(method, base, endpoint, token, *, operations, **kwargs):
        seen['method'] = method
        seen['endpoint'] = endpoint
        seen['ops'] = operations
        return {'id': 1234, 'fields': {'System.Title': 'New thing'}}

    monkeypatch.setattr(api_mod, 'json_patch', fake_patch)
    rc = _run(['wi-create', '--type', 'Task', '--title', 'New thing',
               '--assign', '@me', '--field', 'Priority=2', '--confirm'],
              tmp_config, clean_env)
    assert rc == 0
    assert seen['method'] == 'POST'
    assert seen['endpoint'].endswith('/_apis/wit/workitems/$Task')
    paths = {o['path']: o['value'] for o in seen['ops']}
    assert paths['/fields/System.Title'] == 'New thing'
    assert paths['/fields/System.AssignedTo'] == '@Me'
    # A bare --field name without a dot is namespaced under System.*.
    assert paths['/fields/System.Priority'] == '2'


def test_wi_create_requires_type_and_title(tmp_config, clean_env):
    # precheck_required_args raises UsageError (exit 2) before auth.
    rc = _run(['wi-create', '--title', 'x', '--confirm'], tmp_config, clean_env)
    assert rc == 2


def test_wi_update_builds_patch_and_requires_a_change(monkeypatch, tmp_config, clean_env, capsys):
    seen = {}

    def fake_patch(method, base, endpoint, token, *, operations, **kwargs):
        seen['method'] = method
        seen['endpoint'] = endpoint
        seen['ops'] = operations
        return {'id': 5, 'fields': {'System.State': 'Active'}}

    monkeypatch.setattr(api_mod, 'json_patch', fake_patch)
    rc = _run(['wi-update', '5', '--state', 'Active', '--confirm'], tmp_config, clean_env)
    assert rc == 0
    assert seen['method'] == 'PATCH'
    assert seen['endpoint'] == '_apis/wit/workitems/5'
    assert seen['ops'][0]['value'] == 'Active'


def test_wi_update_with_no_changes_is_usage_error(tmp_config, clean_env):
    rc = _run(['wi-update', '5', '--confirm'], tmp_config, clean_env)
    assert rc == 2


def test_prs_list_applies_status_filter(monkeypatch, tmp_config, clean_env, capsys):
    seen = {}

    def fake_request(method, base, endpoint, token, **kwargs):
        seen['endpoint'] = endpoint
        seen['query'] = kwargs.get('query')
        return {'value': [{'pullRequestId': 1, 'title': 'x', 'status': 'active'}]}

    monkeypatch.setattr(api_mod, 'ado_request', fake_request)
    rc = _run(['prs', '--status', 'active', '--top', '10'], tmp_config, clean_env)
    assert rc == 0
    assert seen['endpoint'] == 'Proj/_apis/git/pullrequests'
    assert seen['query']['searchCriteria.status'] == 'active'
    assert seen['query']['$top'] == 10


def test_prs_show_single(monkeypatch, tmp_config, clean_env, capsys):
    def fake_request(method, base, endpoint, token, **kwargs):
        assert endpoint == 'Proj/_apis/git/pullrequests/42'
        return {'pullRequestId': 42, 'title': 'PR', 'status': 'completed'}

    monkeypatch.setattr(api_mod, 'ado_request', fake_request)
    rc = _run(['prs', '42'], tmp_config, clean_env)
    assert rc == 0
    assert json.loads(capsys.readouterr().out)['id'] == 42


def test_prs_repo_scopes_endpoint(monkeypatch, tmp_config, clean_env, capsys):
    seen = {}

    def fake_request(method, base, endpoint, token, **kwargs):
        seen['endpoint'] = endpoint
        return {'value': []}

    monkeypatch.setattr(api_mod, 'ado_request', fake_request)
    _run(['prs', '--repo', 'NOCOS-Main'], tmp_config, clean_env)
    assert seen['endpoint'] == 'Proj/_apis/git/repositories/NOCOS-Main/pullrequests'


def test_prs_repo_is_url_encoded(monkeypatch, tmp_config, clean_env, capsys):
    """A repo name with reserved chars is encoded so it can't break out of
    its path segment (the '/' becomes %2F, not a new segment)."""
    seen = {}

    def fake_request(method, base, endpoint, token, **kwargs):
        seen['endpoint'] = endpoint
        return {'value': []}

    monkeypatch.setattr(api_mod, 'ado_request', fake_request)
    _run(['prs', '--repo', 'My Repo/sub'], tmp_config, clean_env)
    assert seen['endpoint'] == 'Proj/_apis/git/repositories/My%20Repo%2Fsub/pullrequests'


def test_repos_endpoint(monkeypatch, tmp_config, clean_env, capsys):
    seen = {}

    def fake_request(method, base, endpoint, token, **kwargs):
        seen['endpoint'] = endpoint
        return {'value': [{'id': 'r', 'name': 'Repo'}]}

    monkeypatch.setattr(api_mod, 'ado_request', fake_request)
    rc = _run(['repos'], tmp_config, clean_env)
    assert rc == 0
    assert seen['endpoint'] == 'Proj/_apis/git/repositories'


def test_pipelines_and_runs_endpoints(monkeypatch, tmp_config, clean_env, capsys):
    seen = []

    def fake_request(method, base, endpoint, token, **kwargs):
        seen.append((endpoint, kwargs.get('query')))
        return {'value': []}

    monkeypatch.setattr(api_mod, 'ado_request', fake_request)
    _run(['pipelines'], tmp_config, clean_env)
    _run(['runs', '--pipeline', '8', '--top', '3'], tmp_config, clean_env)
    assert seen[0][0] == 'Proj/_apis/pipelines'
    assert seen[1][0] == 'Proj/_apis/build/builds'
    assert seen[1][1] == {'$top': 3, 'definitions': '8'}


def test_sprints_default_team_name(monkeypatch, tmp_config, clean_env, capsys):
    seen = {}

    def fake_request(method, base, endpoint, token, **kwargs):
        seen['endpoint'] = endpoint
        seen['query'] = kwargs.get('query')
        return {'value': []}

    monkeypatch.setattr(api_mod, 'ado_request', fake_request)
    _run(['sprints', '--current'], tmp_config, clean_env)
    assert seen['endpoint'] == 'Proj/Proj Team/_apis/work/teamsettings/iterations'
    assert seen['query'] == {'$timeframe': 'current'}


def test_api_none_propagates_exit_1(monkeypatch, tmp_config, clean_env):
    monkeypatch.setattr(api_mod, 'ado_request', lambda *a, **k: None)
    rc = _run(['projects'], tmp_config, clean_env)
    assert rc == 1
