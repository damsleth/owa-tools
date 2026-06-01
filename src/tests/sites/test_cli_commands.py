"""Direct command tests for owa-sites. No network; api_mod is stubbed."""

import json

import pytest

from owa_sites import cli

BASE = 'https://h.test'


def test_site_positional(monkeypatch, capsys):
    seen = {}

    def fake_get(base, ep, tok, **k):
        seen['ep'] = ep
        return {'Title': 'T', 'Url': 'u', 'Id': 'i', 'Created': 'c'}

    monkeypatch.setattr(cli.api_mod, 'sp_get', fake_get)
    assert cli.cmd_site(['owa-casa'], {}, 'tok', BASE) == 0
    assert seen['ep'] == 'sites/owa-casa/_api/web?$select=Title,Url,Id,Created'
    assert json.loads(capsys.readouterr().out)['title'] == 'T'


def test_site_flag_and_pretty(monkeypatch, capsys):
    monkeypatch.setattr(cli.api_mod, 'sp_get', lambda base, ep, tok, **k: {'Title': 'T', 'Url': 'u'})
    assert cli.cmd_site(['--site', 'owa-casa', '--pretty'], {}, 'tok', BASE) == 0
    assert 'T' in capsys.readouterr().out


def test_site_default_from_config(monkeypatch, capsys):
    seen = {}
    monkeypatch.setattr(
        cli.api_mod, 'sp_get',
        lambda base, ep, tok, **k: seen.update(ep=ep) or {'Title': 'R'},
    )
    assert cli.cmd_site([], {'default_site': 'pinned'}, 'tok', BASE) == 0
    assert seen['ep'].startswith('sites/pinned/_api/web')


def test_lists_filters_hidden(monkeypatch, capsys):
    monkeypatch.setattr(
        cli.api_mod, 'paginate_sp',
        lambda base, ep, tok, **k: [
            {'Title': 'Documents', 'Id': 'l1', 'ItemCount': 5, 'Hidden': False},
            {'Title': 'Sys', 'Id': 'l2', 'Hidden': True},
        ],
    )
    assert cli.cmd_lists(['--site', 'owa-casa'], {}, 'tok', BASE) == 0
    assert [r['title'] for r in json.loads(capsys.readouterr().out)] == ['Documents']


def test_lists_all(monkeypatch, capsys):
    monkeypatch.setattr(
        cli.api_mod, 'paginate_sp', lambda base, ep, tok, **k: [{'Title': 'Sys', 'Hidden': True}]
    )
    assert cli.cmd_lists(['--all-lists', '--pretty'], {}, 'tok', BASE) == 0
    assert 'Sys' in capsys.readouterr().out


def test_items_requires_list():
    with pytest.raises(cli.UsageError, match='--list is required'):
        cli.cmd_items(['--site', 'x'], {}, 'tok', BASE)


def test_items_strips_odata(monkeypatch, capsys):
    seen = {}

    def fake_paginate(base, ep, tok, **k):
        seen['ep'] = ep
        return [{'Id': 1, 'Title': 'X', 'odata.etag': '"1"'}]

    monkeypatch.setattr(cli.api_mod, 'paginate_sp', fake_paginate)
    assert cli.cmd_items(['--site', 'owa-casa', '--list', 'Documents'], {}, 'tok', BASE) == 0
    assert "getbytitle('Documents')/items" in seen['ep']
    assert json.loads(capsys.readouterr().out) == [{'Id': 1, 'Title': 'X'}]


def test_files_requires_path():
    with pytest.raises(cli.UsageError, match='--path is required'):
        cli.cmd_files(['--site', 'x'], {}, 'tok', BASE)


def test_files(monkeypatch, capsys):
    monkeypatch.setattr(
        cli.api_mod, 'paginate_sp', lambda base, ep, tok, **k: [{'Name': 'a.docx', 'Length': '12'}]
    )
    assert cli.cmd_files(
        ['--site', 'owa-casa', '--path', '/sites/owa-casa/Shared Documents', '--pretty'],
        {}, 'tok', BASE,
    ) == 0
    assert 'a.docx' in capsys.readouterr().out


def test_search_requires_q():
    with pytest.raises(cli.UsageError, match='--q is required'):
        cli.cmd_search([], {}, 'tok', BASE)


def test_search(monkeypatch, capsys):
    monkeypatch.setattr(
        cli.api_mod, 'sp_get',
        lambda base, ep, tok, **k: {
            'PrimaryQueryResult': {
                'RelevantResults': {'Table': {'Rows': [{'Cells': [{'Key': 'Title', 'Value': 'Doc'}]}]}}
            }
        },
    )
    assert cli.cmd_search(['--q', 'budget', '--limit', '5'], {}, 'tok', BASE) == 0
    assert json.loads(capsys.readouterr().out) == [{'Title': 'Doc'}]


def test_data_none_returns_one(monkeypatch):
    monkeypatch.setattr(cli.api_mod, 'sp_get', lambda *a, **k: None)
    assert cli.cmd_site(['x'], {}, 'tok', BASE) == 1
    monkeypatch.setattr(cli.api_mod, 'paginate_sp', lambda *a, **k: None)
    assert cli.cmd_lists([], {}, 'tok', BASE) == 1


def test_unknown_flag_rejected():
    with pytest.raises(cli.UsageError, match='Unknown flag'):
        cli.cmd_site(['--nope'], {}, 'tok', BASE)


def test_config(monkeypatch, capsys):
    saved = {}
    monkeypatch.setattr(cli.config_mod, 'CONFIG_PATH', '/tmp/owa-sites-cfg')
    monkeypatch.setattr(cli.config_mod, 'config_set', lambda k, v: saved.__setitem__(k, v))
    assert cli.cmd_config(
        ['--profile', 'work', '--host', 'contoso.sharepoint.com', '--site', 'owa-casa'], {}
    ) == 0
    assert saved == {
        'owa_piggy_profile': 'work',
        'sharepoint_host': 'contoso.sharepoint.com',
        'default_site': 'owa-casa',
    }
    err = capsys.readouterr().err
    assert 'sharepoint_host saved' in err
    assert cli.cmd_config([], {}) == 0
    assert 'auto-discovered' in capsys.readouterr().err


def test_refresh_ok(monkeypatch, capsys):
    monkeypatch.setattr(cli.auth_mod, 'setup_auth', lambda config, debug=False: ('tok', 'https://h'))
    monkeypatch.setattr(cli.api_mod, 'sp_get', lambda base, ep, tok, **k: {'Title': 'Root', 'Url': 'u'})
    assert cli.cmd_refresh([], {}) == 0
    assert 'Connected to https://h' in capsys.readouterr().err


def test_refresh_auth_failure(monkeypatch, capsys):
    from owa_core.errors import AuthExpiredError

    def boom(config, debug=False):
        raise AuthExpiredError('auth expired (401)')

    monkeypatch.setattr(cli.auth_mod, 'setup_auth', boom)
    assert cli.cmd_refresh([], {}) == 11  # ExitCode.AUTH_EXPIRED
    capsys.readouterr()


def test_refresh_verify_failure(monkeypatch, capsys):
    monkeypatch.setattr(cli.auth_mod, 'setup_auth', lambda config, debug=False: ('tok', 'https://h'))
    monkeypatch.setattr(cli.api_mod, 'sp_get', lambda *a, **k: None)
    assert cli.cmd_refresh([], {}) == 1
    assert 'Auth verification failed' in capsys.readouterr().err
