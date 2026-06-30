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


def test_items_odata_and_all_unbounded(monkeypatch, capsys):
    seen = {}

    def fake_paginate(base, ep, tok, **k):
        seen['ep'] = ep
        seen['max_pages'] = k.get('max_pages')
        return [{'Id': 1}]

    monkeypatch.setattr(cli.api_mod, 'paginate_sp', fake_paginate)
    assert cli.cmd_items(
        ['--list', 'Documents', '--filter', 'Id gt 0', '--orderby', 'Id', '--all'],
        {}, 'tok', BASE,
    ) == 0
    assert '$filter=' in seen['ep']
    assert seen['max_pages'] is None


def test_items_truncation_warns(monkeypatch, capsys):
    def fake_paginate(base, ep, tok, on_truncate=None, **k):
        if on_truncate:
            on_truncate(2, 'https://h/next')
        return [{'Id': 1}]

    monkeypatch.setattr(cli.api_mod, 'paginate_sp', fake_paginate)
    assert cli.cmd_items(['--list', 'Documents', '--max-pages', '2'], {}, 'tok', BASE) == 0
    assert 'stopped after 2 pages' in capsys.readouterr().err


def test_items_max_pages_must_be_positive():
    with pytest.raises(cli.UsageError, match='--max-pages must be >= 1'):
        cli.cmd_items(['--list', 'D', '--max-pages', '0'], {}, 'tok', BASE)


def test_item_by_positional_id(monkeypatch, capsys):
    seen = {}

    def fake_get(base, ep, tok, **k):
        seen['ep'] = ep
        return {'Id': 42, 'Title': 'X', 'odata.etag': '"1"'}

    monkeypatch.setattr(cli.api_mod, 'sp_get', fake_get)
    assert cli.cmd_item(['42', '--site', 'owa-casa', '--list', 'Documents'], {}, 'tok', BASE) == 0
    assert 'items(42)' in seen['ep']
    assert json.loads(capsys.readouterr().out) == {'Id': 42, 'Title': 'X'}


def test_item_requires_list_and_id():
    with pytest.raises(cli.UsageError, match='--list is required'):
        cli.cmd_item(['42'], {}, 'tok', BASE)
    with pytest.raises(cli.UsageError, match='item id is required'):
        cli.cmd_item(['--list', 'Documents'], {}, 'tok', BASE)


def test_item_non_integer_id():
    with pytest.raises(cli.UsageError, match='must be an integer'):
        cli.cmd_item(['abc', '--list', 'Documents'], {}, 'tok', BASE)


def test_item_data_none(monkeypatch):
    monkeypatch.setattr(cli.api_mod, 'sp_get', lambda *a, **k: None)
    assert cli.cmd_item(['1', '--list', 'D'], {}, 'tok', BASE) == 1


def test_file_by_id(monkeypatch, capsys):
    seen = {}

    def fake_get(base, ep, tok, **k):
        seen['ep'] = ep
        return {'Name': 'a.docx', 'Length': '12', 'UniqueId': 'g1'}

    monkeypatch.setattr(cli.api_mod, 'sp_get', fake_get)
    assert cli.cmd_file(['g1', '--site', 'owa-casa'], {}, 'tok', BASE) == 0
    assert "GetFileById('g1')" in seen['ep']
    assert json.loads(capsys.readouterr().out)['name'] == 'a.docx'


def test_file_requires_id():
    with pytest.raises(cli.UsageError, match='file id is required'):
        cli.cmd_file([], {}, 'tok', BASE)


def test_file_data_none(monkeypatch):
    monkeypatch.setattr(cli.api_mod, 'sp_get', lambda *a, **k: None)
    assert cli.cmd_file(['g1'], {}, 'tok', BASE) == 1


def test_site_accepts_url(monkeypatch, capsys):
    seen = {}
    monkeypatch.setattr(
        cli.api_mod, 'sp_get',
        lambda base, ep, tok, **k: seen.update(ep=ep) or {'Title': 'T', 'Url': 'u'},
    )
    assert cli.cmd_site(
        ['https://contoso.sharepoint.com/sites/owa-casa'], {}, 'tok', BASE,
    ) == 0
    assert seen['ep'].startswith('sites/owa-casa/_api/web')


def test_lists_odata_flags(monkeypatch, capsys):
    seen = {}
    monkeypatch.setattr(
        cli.api_mod, 'paginate_sp',
        lambda base, ep, tok, **k: seen.update(ep=ep) or [{'Title': 'A', 'Hidden': False}],
    )
    assert cli.cmd_lists(
        ['--filter', 'Hidden eq false', '--orderby', 'Title', '--expand', 'Fields'],
        {}, 'tok', BASE,
    ) == 0
    assert '$filter=' in seen['ep'] and '$orderby=' in seen['ep'] and '$expand=' in seen['ep']


def test_items_select_top_pretty(monkeypatch, capsys):
    monkeypatch.setattr(cli.api_mod, 'paginate_sp', lambda *a, **k: [{'Title': 'Row'}])
    assert cli.cmd_items(
        ['--list', 'D', '--select', 'Title', '--top', '5', '--pretty'], {}, 'tok', BASE,
    ) == 0
    assert 'Row' in capsys.readouterr().out


def test_item_id_flag_select_expand_pretty(monkeypatch, capsys):
    monkeypatch.setattr(
        cli.api_mod, 'sp_get', lambda *a, **k: {'Id': 7, 'Title': 'Seven'},
    )
    assert cli.cmd_item(
        ['--id', '7', '--list', 'D', '--select', 'Title', '--expand', 'Author', '--pretty'],
        {}, 'tok', BASE,
    ) == 0
    assert 'Seven' in capsys.readouterr().out


def test_item_unknown_flag():
    with pytest.raises(cli.UsageError, match='Unknown flag'):
        cli.cmd_item(['1', '--list', 'D', '--nope'], {}, 'tok', BASE)


def test_file_id_flag_pretty(monkeypatch, capsys):
    monkeypatch.setattr(cli.api_mod, 'sp_get', lambda *a, **k: {'Name': 'b.txt', 'Length': '3'})
    assert cli.cmd_file(['--id', 'g2', '--pretty'], {}, 'tok', BASE) == 0
    assert 'b.txt' in capsys.readouterr().out


def test_file_unknown_flag():
    with pytest.raises(cli.UsageError, match='Unknown flag'):
        cli.cmd_file(['g1', '--nope'], {}, 'tok', BASE)


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


def test_config_unset(monkeypatch, capsys):
    unset = []
    monkeypatch.setattr(cli.config_mod, 'config_unset', lambda k: unset.append(k))
    assert cli.cmd_config(['--unset', 'site', '--unset', 'host'], {}) == 0
    assert unset == ['default_site', 'sharepoint_host']
    assert 'unset: default_site' in capsys.readouterr().err


def test_config_unset_unknown_key():
    with pytest.raises(cli.UsageError, match='unknown config key'):
        cli.cmd_config(['--unset', 'bogus'], {})


def test_config_clear(monkeypatch, capsys):
    cleared = []
    monkeypatch.setattr(cli.config_mod, 'config_clear', lambda: cleared.append(True))
    assert cli.cmd_config(['--clear'], {}) == 0
    assert cleared == [True]
    assert 'config cleared' in capsys.readouterr().err


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
