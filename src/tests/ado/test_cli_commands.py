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


def test_variable_groups_masks_secrets(monkeypatch, tmp_config, clean_env, capsys):
    seen = {}

    def fake_request(method, base, endpoint, token, **kwargs):
        seen['endpoint'] = endpoint
        return {'value': [{
            'id': 3, 'name': 'shared', 'type': 'Vsts',
            'variables': {'API_URL': {'value': 'https://x'},
                          'API_KEY': {'isSecret': True}},
        }]}

    monkeypatch.setattr(api_mod, 'ado_request', fake_request)
    rc = _run(['library'], tmp_config, clean_env)  # alias -> variable-groups
    assert rc == 0
    assert seen['endpoint'] == 'Proj/_apis/distributedtask/variablegroups'
    out = json.loads(capsys.readouterr().out)[0]
    assert out['variables'] == {'API_URL': 'https://x', 'API_KEY': '***'}


def test_variable_group_show_single_json(monkeypatch, tmp_config, clean_env, capsys):
    seen = {}

    def fake_request(method, base, endpoint, token, **kwargs):
        seen['endpoint'] = endpoint
        return {'id': 15, 'name': 'NOCOS-m365-prod', 'type': 'Vsts',
                'variables': {'TENANT': {'value': 't'}, 'SECRET': {'isSecret': True}}}

    monkeypatch.setattr(api_mod, 'ado_request', fake_request)
    rc = _run(['library', '15'], tmp_config, clean_env)
    assert rc == 0
    assert seen['endpoint'] == 'Proj/_apis/distributedtask/variablegroups/15'
    out = json.loads(capsys.readouterr().out)
    assert out['name'] == 'NOCOS-m365-prod'
    assert out['variables'] == {'TENANT': 't', 'SECRET': '***'}


def test_variable_group_show_single_pretty(monkeypatch, tmp_config, clean_env, capsys):
    def fake_request(method, base, endpoint, token, **kwargs):
        return {'id': 15, 'name': 'NOCOS-m365-prod', 'type': 'Vsts',
                'variables': {'TENANT': {'value': 't'}}}

    monkeypatch.setattr(api_mod, 'ado_request', fake_request)
    assert _run(['library', '15', '--pretty'], tmp_config, clean_env) == 0
    out = capsys.readouterr().out
    assert 'NOCOS-m365-prod' in out and 'TENANT' in out and 't' in out


def test_subresource_endpoints(monkeypatch, tmp_config, clean_env, capsys):
    seen = {}

    def fake_request(method, base, endpoint, token, **kwargs):
        seen[endpoint] = base
        return {'value': []}

    monkeypatch.setattr(api_mod, 'ado_request', fake_request)
    for cmd in ('task-groups', 'deployment-groups', 'environments', 'releases'):
        assert _run([cmd], tmp_config, clean_env) == 0
    assert 'Proj/_apis/distributedtask/taskgroups' in seen
    assert 'Proj/_apis/distributedtask/deploymentgroups' in seen
    assert 'Proj/_apis/distributedtask/environments' in seen
    # releases route to the vsrm host, not dev.azure.com
    assert seen['Proj/_apis/release/releases'] == 'https://vsrm.dev.azure.com/Org'


def test_variable_groups_all_paginates(monkeypatch, tmp_config, clean_env, capsys):
    called = {}

    def fake_paginate(base, endpoint, token, **kwargs):
        called['endpoint'] = endpoint
        return [{'id': 1, 'name': 'g', 'variables': {}}]

    monkeypatch.setattr(api_mod, 'ado_paginate', fake_paginate)
    assert _run(['variable-groups', '--all'], tmp_config, clean_env) == 0
    assert called['endpoint'] == 'Proj/_apis/distributedtask/variablegroups'


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




def test_wikis_lists_normalized(monkeypatch, tmp_config, clean_env, capsys):
    seen = {}

    def fake_request(method, base, endpoint, token, **kwargs):
        seen['endpoint'] = endpoint
        return {'value': [{'id': 'w1', 'name': 'NOCOS.wiki', 'type': 'projectWiki'}]}

    monkeypatch.setattr(api_mod, 'ado_request', fake_request)
    rc = _run(['wikis'], tmp_config, clean_env)
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out[0]['name'] == 'NOCOS.wiki'
    assert seen['endpoint'] == 'Proj/_apis/wiki/wikis'


def test_wiki_by_id_includes_content(monkeypatch, tmp_config, clean_env, capsys):
    seen = {}

    def fake_request(method, base, endpoint, token, query=None, **kwargs):
        seen['endpoint'] = endpoint
        seen['query'] = query
        return {'id': 83, 'path': '/NOCOS', 'content': '# hi'}

    monkeypatch.setattr(api_mod, 'ado_request', fake_request)
    rc = _run(['wiki', '--wiki', 'NOCOS.wiki', '--id', '83'], tmp_config, clean_env)
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out['content'] == '# hi'
    assert seen['endpoint'] == 'Proj/_apis/wiki/wikis/NOCOS.wiki/pages/83'
    assert seen['query'] == {'includeContent': 'true'}


def test_wiki_by_positional_path_prepends_slash(monkeypatch, tmp_config, clean_env, capsys):
    seen = {}

    def fake_request(method, base, endpoint, token, query=None, **kwargs):
        seen['endpoint'] = endpoint
        seen['query'] = query
        return {'path': '/Home', 'content': 'body'}

    monkeypatch.setattr(api_mod, 'ado_request', fake_request)
    rc = _run(['wiki', '--wiki', 'W', 'Home'], tmp_config, clean_env)
    assert rc == 0
    assert seen['endpoint'] == 'Proj/_apis/wiki/wikis/W/pages'
    assert seen['query'] == {'path': '/Home', 'includeContent': 'true'}


def test_wiki_tree_when_no_page(monkeypatch, tmp_config, clean_env, capsys):
    seen = {}

    def fake_request(method, base, endpoint, token, query=None, **kwargs):
        seen['query'] = query
        return {'path': '/', 'subPages': [{'path': '/Home'}]}

    monkeypatch.setattr(api_mod, 'ado_request', fake_request)
    rc = _run(['wiki', '--wiki', 'W'], tmp_config, clean_env)
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out['subPages'][0]['path'] == '/Home'
    assert seen['query'] == {'path': '/', 'recursionLevel': 'full'}


def test_wiki_auto_resolves_sole_wiki(monkeypatch, tmp_config, clean_env, capsys):
    calls = []

    def fake_request(method, base, endpoint, token, query=None, **kwargs):
        calls.append(endpoint)
        if endpoint == 'Proj/_apis/wiki/wikis':
            return {'value': [{'id': 'w1', 'name': 'OnlyWiki'}]}
        return {'path': '/', 'subPages': []}

    monkeypatch.setattr(api_mod, 'ado_request', fake_request)
    rc = _run(['wiki'], tmp_config, clean_env)
    assert rc == 0
    # Resolved the sole wiki, then fetched its page tree.
    assert calls[0] == 'Proj/_apis/wiki/wikis'
    assert calls[1] == 'Proj/_apis/wiki/wikis/OnlyWiki/pages'


def test_wiki_ambiguous_without_flag_is_usage_error(monkeypatch, tmp_config, clean_env, capsys):
    def fake_request(method, base, endpoint, token, **kwargs):
        return {'value': [{'name': 'A'}, {'name': 'B'}]}

    monkeypatch.setattr(api_mod, 'ado_request', fake_request)
    rc = _run(['wiki'], tmp_config, clean_env)
    assert rc != 0
    err = capsys.readouterr().err
    assert 'A, B' in err and '--wiki' in err


def test_wiki_pretty_prints_content(monkeypatch, tmp_config, clean_env, capsys):
    monkeypatch.setattr(api_mod, 'ado_request',
                        lambda *a, **k: {'id': 1, 'path': '/P', 'content': 'BODY'})
    rc = _run(['wiki', '--wiki', 'W', '--id', '1', '--pretty'], tmp_config, clean_env)
    assert rc == 0
    out = capsys.readouterr().out
    assert out.startswith('# /P (id 1)') and 'BODY' in out


def test_wiki_path_flag(monkeypatch, tmp_config, clean_env):
    seen = {}

    def fake_request(method, base, endpoint, token, query=None, **kwargs):
        seen['query'] = query
        return {'path': '/Deep/Page', 'content': 'x'}

    monkeypatch.setattr(api_mod, 'ado_request', fake_request)
    assert _run(['wiki', '--wiki', 'W', '--path', '/Deep/Page'], tmp_config, clean_env) == 0
    assert seen['query'] == {'path': '/Deep/Page', 'includeContent': 'true'}


def test_wiki_unknown_flag_and_extra_arg_are_usage_errors(monkeypatch, tmp_config, clean_env):
    monkeypatch.setattr(api_mod, 'ado_request', lambda *a, **k: {'value': [{'name': 'W'}]})
    assert _run(['wiki', '--nope'], tmp_config, clean_env) != 0
    assert _run(['wiki', 'a', 'b'], tmp_config, clean_env) != 0


def test_wikis_returns_1_on_bad_payload(monkeypatch, tmp_config, clean_env):
    monkeypatch.setattr(api_mod, 'ado_request', lambda *a, **k: 'not-a-dict')
    assert _run(['wikis'], tmp_config, clean_env) == 1


def test_wiki_returns_1_on_bad_payload(monkeypatch, tmp_config, clean_env):
    monkeypatch.setattr(api_mod, 'ado_request', lambda *a, **k: 'nope')
    assert _run(['wiki', '--wiki', 'W', '--id', '1'], tmp_config, clean_env) == 1


def _wiki_tree_and_pages(tree, contents):
    """Fake ado_request: recursionLevel call returns `tree`; per-page path
    calls return {'content': contents[path]}."""
    def fake(method, base, endpoint, token, query=None, **kwargs):
        if query and query.get('recursionLevel') == 'full':
            return tree
        return {'content': contents.get((query or {}).get('path'), '')}
    return fake


def test_wiki_download_mirrors_tree_to_disk(monkeypatch, tmp_config, clean_env, capsys, tmp_path):
    tree = {
        'path': '/', 'gitItemPath': '/', 'subPages': [
            {'path': '/Home', 'gitItemPath': '/Home.md', 'subPages': [
                {'path': '/Home/Sub', 'gitItemPath': '/Home/Sub.md', 'subPages': []},
            ]},
        ],
    }
    contents = {'/Home': '# Home', '/Home/Sub': '# Sub'}
    monkeypatch.setattr(api_mod, 'ado_request', _wiki_tree_and_pages(tree, contents))
    out_dir = tmp_path / 'wiki'
    rc = _run(['wiki', '--wiki', 'W', '--download', str(out_dir)], tmp_config, clean_env)
    assert rc == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary['downloaded'] == 2
    assert (out_dir / 'Home.md').read_text() == '# Home'
    assert (out_dir / 'Home' / 'Sub.md').read_text() == '# Sub'
    # The root/folder page (no .md gitItemPath) is not written.
    assert not (out_dir / '.md').exists()


def test_wiki_download_skips_path_traversal(monkeypatch, tmp_config, clean_env, tmp_path):
    tree = {
        'path': '/', 'gitItemPath': '/', 'subPages': [
            {'path': '/evil', 'gitItemPath': '/../evil.md', 'subPages': []},
            {'path': '/ok', 'gitItemPath': '/ok.md', 'subPages': []},
        ],
    }
    monkeypatch.setattr(api_mod, 'ado_request',
                        _wiki_tree_and_pages(tree, {'/ok': 'safe'}))
    out_dir = tmp_path / 'wiki'
    rc = _run(['wiki', '--wiki', 'W', '--download', str(out_dir)], tmp_config, clean_env)
    assert rc == 0
    assert (out_dir / 'ok.md').read_text() == 'safe'
    assert not (tmp_path / 'evil.md').exists()


def test_wiki_download_pretty_lists_files(monkeypatch, tmp_config, clean_env, capsys, tmp_path):
    tree = {'path': '/', 'gitItemPath': '/', 'subPages': [
        {'path': '/A', 'gitItemPath': '/A.md', 'subPages': []}]}
    monkeypatch.setattr(api_mod, 'ado_request',
                        _wiki_tree_and_pages(tree, {'/A': 'x'}))
    rc = _run(['wiki', '--wiki', 'W', '--download', str(tmp_path / 'w'), '--pretty'],
              tmp_config, clean_env)
    assert rc == 0
    out = capsys.readouterr().out
    assert '1 page(s) ->' in out and 'A.md' in out


def test_wiki_download_returns_1_on_bad_tree(monkeypatch, tmp_config, clean_env, tmp_path):
    monkeypatch.setattr(api_mod, 'ado_request', lambda *a, **k: 'nope')
    rc = _run(['wiki', '--wiki', 'W', '--download', str(tmp_path / 'w')], tmp_config, clean_env)
    assert rc == 1
