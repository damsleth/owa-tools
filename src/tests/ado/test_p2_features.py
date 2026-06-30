"""P2 feature coverage for owa-ado.

- `--all` continuation paging on `prs` / `runs` (cap + truncation note)
- work-item `wi-comment`, `wi-link`, `wi-unlink`, `wi-delete`
- `--api-version` override
- `config --unset` / `config --clear`

Auth and the network layer are stubbed; no network.
"""
import json

import pytest

from owa_ado import api as api_mod
from owa_ado import auth as auth_mod
from owa_ado import cli as cli_mod
from owa_ado import config as config_mod
from owa_core import tty as tty_mod


@pytest.fixture(autouse=True)
def _stub_auth(monkeypatch):
    monkeypatch.setattr(auth_mod, 'setup_auth', lambda config, debug=False: 'tok')


@pytest.fixture(autouse=True)
def _auto_confirm(monkeypatch):
    # Default the TTY gate open; tests that exercise abort override it.
    monkeypatch.setattr(tty_mod, 'require_confirm_or_tty', lambda *, action: None)
    monkeypatch.setattr(tty_mod, 'confirm', lambda *a, **k: True)


def _run(argv, tmp_config, clean_env):
    return cli_mod.main(['--org', 'Org', '--project', 'Proj', *argv])


# --- --all paging on prs / runs ----------------------------------------

def test_prs_all_paginates_with_cap(monkeypatch, tmp_config, clean_env):
    seen = {}

    def fake_paginate(base, endpoint, token, **kwargs):
        seen['endpoint'] = endpoint
        seen['query'] = kwargs.get('query')
        seen['max_items'] = kwargs.get('max_items')
        return [{'pullRequestId': 1}, {'pullRequestId': 2}]

    monkeypatch.setattr(api_mod, 'ado_paginate', fake_paginate)
    rc = _run(['prs', '--all', '--status', 'completed', '--top', '5'],
              tmp_config, clean_env)
    assert rc == 0
    assert seen['endpoint'] == 'Proj/_apis/git/pullrequests'
    assert seen['query'] == {'searchCriteria.status': 'completed'}
    assert seen['max_items'] == 5


def test_prs_all_emits_truncation_note(monkeypatch, tmp_config, clean_env, capsys):
    monkeypatch.setattr(api_mod, 'ado_paginate',
                        lambda *a, **k: [{'pullRequestId': i} for i in range(2)])
    rc = _run(['prs', '--all', '--top', '2'], tmp_config, clean_env)
    assert rc == 0
    assert 'capped at 2' in capsys.readouterr().err


def test_runs_all_paginates(monkeypatch, tmp_config, clean_env):
    seen = {}
    monkeypatch.setattr(api_mod, 'ado_paginate',
                        lambda base, ep, t, **k: seen.update(ep=ep, mx=k.get('max_items')) or [])
    rc = _run(['runs', '--all', '--top', '50'], tmp_config, clean_env)
    assert rc == 0
    assert seen['ep'] == 'Proj/_apis/build/builds'
    assert seen['mx'] == 50


def test_prs_without_all_single_page(monkeypatch, tmp_config, clean_env):
    seen = {}
    monkeypatch.setattr(api_mod, 'ado_request',
                        lambda m, base, ep, t, **k: seen.update(q=k.get('query')) or {'value': []})
    assert _run(['prs', '--top', '7'], tmp_config, clean_env) == 0
    assert seen['q'] == {'$top': 7}


# --- --api-version override --------------------------------------------

def test_prs_api_version_override(monkeypatch, tmp_config, clean_env):
    seen = {}
    monkeypatch.setattr(api_mod, 'ado_request',
                        lambda m, base, ep, t, **k: seen.update(v=k.get('api_version')) or {'value': []})
    assert _run(['prs', '--api-version', '7.0'], tmp_config, clean_env) == 0
    assert seen['v'] == '7.0'


def test_runs_api_version_default_when_absent(monkeypatch, tmp_config, clean_env):
    seen = {}
    monkeypatch.setattr(api_mod, 'ado_request',
                        lambda m, base, ep, t, **k: seen.update(v=k.get('api_version')) or {'value': []})
    assert _run(['runs'], tmp_config, clean_env) == 0
    assert seen['v'] == api_mod.DEFAULT_API_VERSION


# --- wi-comment --------------------------------------------------------

def test_wi_comment_posts_text(monkeypatch, tmp_config, clean_env, capsys):
    seen = {}

    def fake_request(method, base, endpoint, token, **kwargs):
        seen['method'] = method
        seen['endpoint'] = endpoint
        seen['body'] = kwargs.get('body')
        seen['version'] = kwargs.get('api_version')
        return {'id': 3, 'workItemId': 17054, 'text': 'hi',
                'createdBy': {'displayName': 'Kim'}}

    monkeypatch.setattr(api_mod, 'ado_request', fake_request)
    rc = _run(['wi-comment', '17054', '--text', 'hi', '--confirm'], tmp_config, clean_env)
    assert rc == 0
    assert seen['method'] == 'POST'
    assert seen['endpoint'] == 'Proj/_apis/wit/workItems/17054/comments'
    assert seen['body'] == {'text': 'hi'}
    assert seen['version'] == '7.1-preview.4'
    out = json.loads(capsys.readouterr().out)
    assert out['id'] == 3 and out['createdBy'] == 'Kim'


def test_wi_comment_requires_text(tmp_config, clean_env):
    assert _run(['wi-comment', '17054', '--confirm'], tmp_config, clean_env) == 2


def test_wi_comment_requires_id(tmp_config, clean_env):
    assert _run(['wi-comment', '--text', 'x', '--confirm'], tmp_config, clean_env) == 2


def test_wi_comment_aborts_on_no(monkeypatch, tmp_config, clean_env):
    monkeypatch.setattr(tty_mod, 'confirm', lambda *a, **k: False)
    monkeypatch.setattr(api_mod, 'ado_request',
                        lambda *a, **k: pytest.fail('must not write on abort'))
    assert _run(['wi-comment', '5', '--text', 'x'], tmp_config, clean_env) == 1


# --- wi-link -----------------------------------------------------------

def test_wi_link_builds_relation_patch(monkeypatch, tmp_config, clean_env):
    seen = {}

    def fake_patch(method, base, endpoint, token, *, operations, **kwargs):
        seen['method'] = method
        seen['endpoint'] = endpoint
        seen['ops'] = operations
        return {'id': 5, 'fields': {}}

    monkeypatch.setattr(api_mod, 'json_patch', fake_patch)
    rc = _run(['wi-link', '5', '--target', '42', '--rel', 'parent', '--confirm'],
              tmp_config, clean_env)
    assert rc == 0
    assert seen['method'] == 'PATCH'
    assert seen['endpoint'] == '_apis/wit/workitems/5'
    op = seen['ops'][0]
    assert op['op'] == 'add' and op['path'] == '/relations/-'
    assert op['value']['rel'] == 'System.LinkTypes.Hierarchy-Reverse'
    assert op['value']['url'].endswith('/_apis/wit/workItems/42')


def test_wi_link_defaults_to_related(monkeypatch, tmp_config, clean_env):
    seen = {}
    monkeypatch.setattr(api_mod, 'json_patch',
                        lambda *a, operations, **k: seen.update(ops=operations) or {'id': 1, 'fields': {}})
    assert _run(['wi-link', '5', '--target', '9', '--confirm'], tmp_config, clean_env) == 0
    assert seen['ops'][0]['value']['rel'] == 'System.LinkTypes.Related'


def test_wi_link_requires_target(tmp_config, clean_env):
    assert _run(['wi-link', '5', '--confirm'], tmp_config, clean_env) == 2


def test_wi_link_unknown_flag(monkeypatch, tmp_config, clean_env):
    monkeypatch.setattr(api_mod, 'json_patch', lambda *a, **k: {'id': 1, 'fields': {}})
    assert _run(['wi-link', '5', '--target', '9', '--nope', '--confirm'],
                tmp_config, clean_env) == 2


def test_wi_link_unexpected_positional(monkeypatch, tmp_config, clean_env):
    monkeypatch.setattr(api_mod, 'json_patch', lambda *a, **k: {'id': 1, 'fields': {}})
    assert _run(['wi-link', '5', '6', '--target', '9', '--confirm'],
                tmp_config, clean_env) == 2


def test_wi_link_aborts_on_no(monkeypatch, tmp_config, clean_env):
    monkeypatch.setattr(tty_mod, 'confirm', lambda *a, **k: False)
    monkeypatch.setattr(api_mod, 'json_patch',
                        lambda *a, **k: pytest.fail('must not link on abort'))
    assert _run(['wi-link', '5', '--target', '9'], tmp_config, clean_env) == 1


# --- wi-unlink ---------------------------------------------------------

def test_wi_unlink_removes_matching_relation_by_index(monkeypatch, tmp_config, clean_env):
    calls = []

    def fake_request(method, base, endpoint, token, **kwargs):
        calls.append((method, endpoint, kwargs.get('query')))
        return {
            'id': 5,
            'relations': [
                {'rel': 'System.LinkTypes.Related',
                 'url': 'https://dev.azure.com/Org/_apis/wit/workItems/99'},
                {'rel': 'System.LinkTypes.Related',
                 'url': 'https://dev.azure.com/Org/_apis/wit/workItems/42'},
            ],
        }

    seen = {}

    def fake_patch(method, base, endpoint, token, *, operations, **kwargs):
        seen['ops'] = operations
        return {'id': 5, 'fields': {}}

    monkeypatch.setattr(api_mod, 'ado_request', fake_request)
    monkeypatch.setattr(api_mod, 'json_patch', fake_patch)
    rc = _run(['wi-unlink', '5', '--target', '42', '--confirm'], tmp_config, clean_env)
    assert rc == 0
    # Fetched relations with $expand, then removed the index of the #42 link.
    assert calls[0][2] == {'$expand': 'relations'}
    assert seen['ops'] == [{'op': 'remove', 'path': '/relations/1'}]


def test_wi_unlink_prompts_then_removes(monkeypatch, tmp_config, clean_env):
    """Without --confirm, the TTY gate runs before the remove patch fires."""
    monkeypatch.setattr(api_mod, 'ado_request', lambda *a, **k: {
        'id': 5, 'relations': [
            {'rel': 'System.LinkTypes.Related', 'url': 'https://x/_apis/wit/workItems/42'},
        ],
    })
    seen = {}
    monkeypatch.setattr(api_mod, 'json_patch',
                        lambda *a, operations, **k: seen.update(ops=operations) or {'id': 5, 'fields': {}})
    rc = _run(['wi-unlink', '5', '--target', '42'], tmp_config, clean_env)
    assert rc == 0
    assert seen['ops'] == [{'op': 'remove', 'path': '/relations/0'}]


def test_wi_unlink_api_version_threads_through(monkeypatch, tmp_config, clean_env):
    seen = {}

    def fake_request(method, base, endpoint, token, **kwargs):
        seen.setdefault('versions', []).append(kwargs.get('api_version'))
        return {'id': 5, 'relations': [
            {'rel': 'System.LinkTypes.Related', 'url': 'https://x/_apis/wit/workItems/42'},
        ]}

    monkeypatch.setattr(api_mod, 'ado_request', fake_request)
    monkeypatch.setattr(api_mod, 'json_patch',
                        lambda *a, api_version=None, **k: seen.update(patch_ver=api_version) or {'id': 5, 'fields': {}})
    assert _run(['wi-unlink', '5', '--target', '42', '--api-version', '7.0', '--confirm'],
                tmp_config, clean_env) == 0
    assert seen['versions'] == ['7.0']
    assert seen['patch_ver'] == '7.0'


def test_wi_delete_api_version_override(monkeypatch, tmp_config, clean_env):
    seen = {}
    monkeypatch.setattr(api_mod, 'ado_request',
                        lambda m, base, ep, t, **k: seen.update(v=k.get('api_version')) or {})
    assert _run(['wi-delete', '5', '--api-version', '7.0', '--confirm'],
                tmp_config, clean_env) == 0
    assert seen['v'] == '7.0'


def test_wi_unlink_missing_link_is_not_found(monkeypatch, tmp_config, clean_env):
    monkeypatch.setattr(api_mod, 'ado_request',
                        lambda *a, **k: {'id': 5, 'relations': []})
    monkeypatch.setattr(api_mod, 'json_patch',
                        lambda *a, **k: pytest.fail('must not patch when link absent'))
    # NotFoundError maps to exit 13.
    assert _run(['wi-unlink', '5', '--target', '42', '--confirm'], tmp_config, clean_env) == 13


def test_wi_unlink_unknown_flag(monkeypatch, tmp_config, clean_env):
    monkeypatch.setattr(api_mod, 'ado_request', lambda *a, **k: {'relations': []})
    assert _run(['wi-unlink', '5', '--target', '9', '--nope', '--confirm'],
                tmp_config, clean_env) == 2


def test_wi_unlink_unexpected_positional(monkeypatch, tmp_config, clean_env):
    monkeypatch.setattr(api_mod, 'ado_request', lambda *a, **k: {'relations': []})
    assert _run(['wi-unlink', '5', '6', '--target', '9', '--confirm'],
                tmp_config, clean_env) == 2


def test_wi_unlink_aborts_on_no(monkeypatch, tmp_config, clean_env):
    monkeypatch.setattr(tty_mod, 'confirm', lambda *a, **k: False)
    monkeypatch.setattr(api_mod, 'ado_request', lambda *a, **k: {
        'id': 5, 'relations': [
            {'rel': 'System.LinkTypes.Related', 'url': 'https://x/_apis/wit/workItems/42'},
        ],
    })
    monkeypatch.setattr(api_mod, 'json_patch',
                        lambda *a, **k: pytest.fail('must not patch on abort'))
    assert _run(['wi-unlink', '5', '--target', '42'], tmp_config, clean_env) == 1


def test_wi_unlink_rel_narrows_match(monkeypatch, tmp_config, clean_env):
    monkeypatch.setattr(api_mod, 'ado_request', lambda *a, **k: {
        'id': 5,
        'relations': [
            {'rel': 'System.LinkTypes.Related',
             'url': 'https://x/_apis/wit/workItems/42'},
        ],
    })
    monkeypatch.setattr(api_mod, 'json_patch',
                        lambda *a, **k: pytest.fail('rel mismatch should not patch'))
    # Asking for a parent link to #42 when only a related link exists -> 13.
    assert _run(['wi-unlink', '5', '--target', '42', '--rel', 'parent', '--confirm'],
                tmp_config, clean_env) == 13


# --- wi-delete ---------------------------------------------------------

def test_wi_delete_soft_delete(monkeypatch, tmp_config, clean_env, capsys):
    seen = {}

    def fake_request(method, base, endpoint, token, **kwargs):
        seen['method'] = method
        seen['endpoint'] = endpoint
        seen['query'] = kwargs.get('query')
        return {'id': 17054, 'code': 200}

    monkeypatch.setattr(api_mod, 'ado_request', fake_request)
    rc = _run(['wi-delete', '17054', '--confirm'], tmp_config, clean_env)
    assert rc == 0
    assert seen['method'] == 'DELETE'
    assert seen['endpoint'] == 'Proj/_apis/wit/workitems/17054'
    assert seen['query'] is None
    out = json.loads(capsys.readouterr().out)
    assert out == {'id': '17054', 'deleted': True, 'destroyed': False, 'code': 200}


def test_wi_delete_destroy_sets_query(monkeypatch, tmp_config, clean_env, capsys):
    seen = {}
    monkeypatch.setattr(api_mod, 'ado_request',
                        lambda m, base, ep, t, **k: seen.update(q=k.get('query')) or {})
    rc = _run(['wi-delete', '5', '--destroy', '--confirm'], tmp_config, clean_env)
    assert rc == 0
    assert seen['q'] == {'destroy': 'true'}
    assert json.loads(capsys.readouterr().out)['destroyed'] is True


def test_wi_delete_aborts_on_no(monkeypatch, tmp_config, clean_env):
    monkeypatch.setattr(tty_mod, 'confirm', lambda *a, **k: False)
    monkeypatch.setattr(api_mod, 'ado_request',
                        lambda *a, **k: pytest.fail('must not delete on abort'))
    assert _run(['wi-delete', '5'], tmp_config, clean_env) == 1


def test_wi_delete_non_tty_is_usage_error(monkeypatch, tmp_config, clean_env):
    from owa_core.errors import UsageError

    def boom(*, action):
        raise UsageError('not a tty; pass --confirm')

    monkeypatch.setattr(tty_mod, 'require_confirm_or_tty', boom)
    assert _run(['wi-delete', '5'], tmp_config, clean_env) == 2


def test_wi_delete_requires_id(tmp_config, clean_env):
    assert _run(['wi-delete', '--confirm'], tmp_config, clean_env) == 2


def test_wi_delete_unknown_flag(monkeypatch, tmp_config, clean_env):
    monkeypatch.setattr(api_mod, 'ado_request', lambda *a, **k: {})
    assert _run(['wi-delete', '5', '--nope', '--confirm'], tmp_config, clean_env) == 2


def test_wi_delete_unexpected_positional(monkeypatch, tmp_config, clean_env):
    monkeypatch.setattr(api_mod, 'ado_request', lambda *a, **k: {})
    assert _run(['wi-delete', '5', '6', '--confirm'], tmp_config, clean_env) == 2


def test_wi_comment_unknown_flag(monkeypatch, tmp_config, clean_env):
    monkeypatch.setattr(api_mod, 'ado_request', lambda *a, **k: {})
    assert _run(['wi-comment', '5', '--text', 'x', '--nope', '--confirm'],
                tmp_config, clean_env) == 2


# --- config --unset / --clear ------------------------------------------

def test_config_unset_removes_one_key(tmp_config, clean_env, capsys):
    assert cli_mod.main(['config', '--org', 'O', '--project', 'P']) == 0
    assert cli_mod.main(['config', '--unset', 'ado_project']) == 0
    assert 'unset ado_project' in capsys.readouterr().err
    text = tmp_config.read_text()
    assert 'ado_org="O"' in text
    assert 'ado_project' not in text


def test_config_unset_unknown_key_is_usage_error(tmp_config, clean_env):
    assert cli_mod.main(['config', '--unset', 'bogus']) == 2


def test_config_unset_absent_key_reports_not_set(tmp_config, clean_env, capsys):
    assert cli_mod.main(['config', '--unset', 'ado_org']) == 0
    assert 'ado_org was not set' in capsys.readouterr().err


def test_config_clear_removes_all(tmp_config, clean_env, capsys):
    assert cli_mod.main(['config', '--org', 'O', '--project', 'P']) == 0
    assert cli_mod.main(['config', '--clear']) == 0
    assert 'config cleared' in capsys.readouterr().err
    assert tmp_config.read_text().strip() == ''


def test_config_clear_on_missing_file(tmp_config, clean_env, capsys):
    assert cli_mod.main(['config', '--clear']) == 0
    assert '0 key(s)' in capsys.readouterr().err


# --- config helpers directly -------------------------------------------

def test_config_unset_returns_false_when_file_missing(tmp_config, clean_env):
    assert config_mod.config_unset('ado_org') is False


def test_config_unset_returns_false_when_key_absent(tmp_config, clean_env):
    # File exists with one key; unsetting a different (allowed) key is a no-op.
    config_mod.config_set('ado_org', 'O')
    assert config_mod.config_unset('ado_project') is False
    assert 'ado_org="O"' in tmp_config.read_text()


def test_config_unset_rejects_unknown_key(tmp_config, clean_env):
    with pytest.raises(ValueError):
        config_mod.config_unset('nope')
