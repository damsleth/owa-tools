"""Direct command tests for owa-planner. No network; api_mod is stubbed."""

import json

import pytest

from owa_planner import cli

BASE = 'https://graph.test'


def _raw_plan(pid='p1', title='Team'):
    return {'id': pid, 'title': title, 'owner': 'g1', 'createdDateTime': '2026-06-01T00:00:00Z'}


def _raw_task(tid='t1', title='Draft', pct=50, bucket='b1'):
    return {
        'id': tid, 'planId': 'p1', 'bucketId': bucket, 'title': title,
        'percentComplete': pct, 'priority': 5, 'assignments': {},
    }


def test_plans(monkeypatch, capsys):
    monkeypatch.setattr(
        cli.api_mod, 'api_get',
        lambda base, ep, tok, **k: {'value': [_raw_plan(), _raw_plan('p2', 'Work')]},
    )
    assert cli.cmd_plans([], {}, 'tok', BASE) == 0
    rows = json.loads(capsys.readouterr().out)
    assert [r['title'] for r in rows] == ['Team', 'Work']
    assert cli.cmd_plans(['--pretty'], {}, 'tok', BASE) == 0
    assert 'Team' in capsys.readouterr().out


def test_plans_group_endpoint(monkeypatch):
    seen = {}

    def fake_get(base, ep, tok, **k):
        seen['ep'] = ep
        return {'value': []}

    monkeypatch.setattr(cli.api_mod, 'api_get', fake_get)
    assert cli.cmd_plans(['--group', 'g9'], {}, 'tok', BASE) == 0
    assert seen['ep'] == 'groups/g9/planner/plans'


def test_buckets_requires_plan():
    with pytest.raises(cli.UsageError, match='--plan is required'):
        cli.cmd_buckets([], {}, 'tok', BASE)


def test_buckets(monkeypatch, capsys):
    seen = {}

    def fake_get(base, ep, tok, **k):
        seen['ep'] = ep
        return {'value': [{'id': 'b1', 'name': 'Doing', 'planId': 'p1', 'orderHint': 'x'}]}

    monkeypatch.setattr(cli.api_mod, 'api_get', fake_get)
    assert cli.cmd_buckets(['--plan', 'p1'], {}, 'tok', BASE) == 0
    assert seen['ep'] == 'planner/plans/p1/buckets'
    assert json.loads(capsys.readouterr().out)[0]['name'] == 'Doing'


def test_buckets_default_plan_from_config(monkeypatch, capsys):
    seen = {}
    monkeypatch.setattr(
        cli.api_mod, 'api_get',
        lambda base, ep, tok, **k: seen.update(ep=ep) or {'value': []},
    )
    assert cli.cmd_buckets([], {'default_plan': 'pX'}, 'tok', BASE) == 0
    assert seen['ep'] == 'planner/plans/pX/buckets'


def test_tasks_default_is_my_tasks(monkeypatch, capsys):
    seen = {}

    def fake_get(base, ep, tok, **k):
        seen['ep'] = ep
        return {'value': [_raw_task(), _raw_task('t2', 'Done', 100, 'b2')]}

    monkeypatch.setattr(cli.api_mod, 'api_get', fake_get)
    assert cli.cmd_tasks([], {}, 'tok', BASE) == 0
    assert seen['ep'] == 'me/planner/tasks'
    rows = json.loads(capsys.readouterr().out)
    assert {r['title'] for r in rows} == {'Draft', 'Done'}


def test_tasks_plan_status_and_bucket_filters(monkeypatch, capsys):
    monkeypatch.setattr(
        cli.api_mod, 'api_get',
        lambda base, ep, tok, **k: {
            'value': [_raw_task('t1', 'A', 0, 'b1'), _raw_task('t2', 'B', 100, 'b2')]
        },
    )
    assert cli.cmd_tasks(['--plan', 'p1', '--status', 'completed'], {}, 'tok', BASE) == 0
    assert [r['title'] for r in json.loads(capsys.readouterr().out)] == ['B']

    monkeypatch.setattr(
        cli.api_mod, 'api_get',
        lambda base, ep, tok, **k: {
            'value': [_raw_task('t1', 'A', 0, 'b1'), _raw_task('t2', 'B', 0, 'b2')]
        },
    )
    assert cli.cmd_tasks(['--plan', 'p1', '--bucket', 'b2'], {}, 'tok', BASE) == 0
    assert [r['title'] for r in json.loads(capsys.readouterr().out)] == ['B']

    monkeypatch.setattr(
        cli.api_mod, 'api_get',
        lambda base, ep, tok, **k: {'value': [_raw_task('t2', 'B', 100, 'b2')]},
    )
    assert cli.cmd_tasks(['--plan', 'p1', '--pretty'], {}, 'tok', BASE) == 0
    assert '[x]' in capsys.readouterr().out


def test_task_merges_details(monkeypatch, capsys):
    def fake_get(base, ep, tok, **k):
        if ep.endswith('/details'):
            return {
                'description': 'desc',
                'checklist': {'c1': {'title': 'step', 'isChecked': True}},
                'references': {},
            }
        return _raw_task('t1', 'Draft', 50, 'b1')

    monkeypatch.setattr(cli.api_mod, 'api_get', fake_get)
    assert cli.cmd_task(['t1'], {}, 'tok', BASE) == 0
    out = json.loads(capsys.readouterr().out)
    assert out['title'] == 'Draft'
    assert out['detail']['description'] == 'desc'

    assert cli.cmd_task(['--id', 't1', '--pretty'], {}, 'tok', BASE) == 0
    assert '[x] step' in capsys.readouterr().out


def test_task_requires_id():
    with pytest.raises(cli.UsageError, match='--id is required'):
        cli.cmd_task([], {}, 'tok', BASE)


def test_unknown_flag_rejected():
    with pytest.raises(cli.UsageError, match='Unknown flag'):
        cli.cmd_plans(['--nope'], {}, 'tok', BASE)


def test_config_and_refresh(monkeypatch, capsys):
    saved = {}
    monkeypatch.setattr(cli.config_mod, 'CONFIG_PATH', '/tmp/owa-planner-config')
    monkeypatch.setattr(
        cli.config_mod, 'config_set', lambda key, value: saved.__setitem__(key, value)
    )
    assert cli.cmd_config(['--profile', 'work', '--plan', 'pX'], {}) == 0
    assert saved == {'owa_piggy_profile': 'work', 'default_plan': 'pX'}
    err = capsys.readouterr().err
    assert 'default profile saved' in err and 'default plan saved' in err
    assert cli.cmd_config([], {'default_plan': 'pX'}) == 0
    assert 'default_plan=pX' in capsys.readouterr().err

    monkeypatch.setattr(cli.auth_mod, 'do_token_refresh', lambda config, debug=False: 'tok')
    monkeypatch.setattr(cli.api_mod, 'api_get', lambda *a, **k: {'displayName': 'Ada'})
    assert cli.cmd_refresh([], {}) == 0
    assert 'Authenticated as Ada' in capsys.readouterr().err
    monkeypatch.setattr(cli.auth_mod, 'do_token_refresh', lambda config, debug=False: '')
    assert cli.cmd_refresh([], {}) == 1
    assert 'Token refresh failed' in capsys.readouterr().err
