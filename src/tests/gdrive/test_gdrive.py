"""owa-gdrive: query builder, export choice, normalizer, CLI and auth. No network."""
import json

import pytest

from owa_core.auth import BrokerToken
from owa_core.errors import AuthExpiredError, ConflictError, UsageError
from owa_gdrive import api, auth, cli, files, format

BASE = 'https://drive.test/v3'
DOC_MIME = 'application/vnd.google-apps.document'


# --- files.py ------------------------------------------------------------


def test_build_list_query_escapes_drive_style():
    q = files.build_list_query(folder='root', name="O'Brien's", search='a\\b', file_type='file')
    assert q == (
        "trashed = false and 'root' in parents and name contains 'O\\'Brien\\'s' "
        "and fullText contains 'a\\\\b' and mimeType != 'application/vnd.google-apps.folder'"
    )
    assert files.build_list_query(file_type='folder', shared=True) == (
        "trashed = false and sharedWithMe and mimeType = 'application/vnd.google-apps.folder'"
    )
    assert files.build_list_query(name='x', raw_query='raw') == 'raw'


@pytest.mark.parametrize('mime, override, expected', [
    (DOC_MIME, None, 'text/plain'),
    ('application/vnd.google-apps.spreadsheet', None, 'text/csv'),
    ('application/vnd.google-apps.presentation', None, 'text/plain'),
    (DOC_MIME, 'application/pdf', 'application/pdf'),
    ('application/pdf', None, None),
    ('application/pdf', 'text/plain', None),
])
def test_resolve_export_mime(mime, override, expected):
    assert files.resolve_export_mime(mime, override) == expected


def test_resolve_export_mime_without_default_raises():
    with pytest.raises(ValueError, match='export-mime'):
        files.resolve_export_mime('application/vnd.google-apps.form')


def test_normalize_file_regular_folder_and_native():
    regular = files.normalize_file({
        'id': 'f1', 'name': 'a.pdf', 'mimeType': 'application/pdf', 'size': '10',
        'modifiedTime': '2026-01-01T00:00:00Z', 'parents': ['root'],
        'owners': [{'emailAddress': 'me@x'}], 'createdTime': '2025-01-01T00:00:00Z',
    })
    assert (regular['kind'], regular['size'], regular['owners'], regular['created']) == ('file', 10, ['me@x'], '2025-01-01T00:00:00Z')
    folder = files.normalize_file({'id': 'd', 'mimeType': files.FOLDER_MIME})
    assert folder['kind'] == 'folder' and folder['is_google_native'] and folder['size'] is None
    assert 'created' not in folder


# --- api.py --------------------------------------------------------------


def test_api_urls_and_paginate(monkeypatch):
    from types import SimpleNamespace

    seen = []
    monkeypatch.setattr(api.http, 'request', lambda m, url, **kw: seen.append((url, kw.get('raw'))) or SimpleNamespace(json={}, bytes=b'xy'))
    api.api_get(BASE, 'files/1', 'tok', params={'fields': 'id'})
    assert api.api_get_bytes(BASE, 'files/1', 'tok', params={'alt': 'media'}) == b'xy'
    assert seen == [(f'{BASE}/files/1?fields=id', None), (f'{BASE}/files/1?alt=media', True)]
    got = {}
    monkeypatch.setattr(api.http, 'paginate_by_token', lambda url, **kw: got.update(url=url, **kw) or ([], None))
    api.paginate(BASE, 'files', 'tok', {'q': 'x'}, max_pages=1)
    assert got['url'] == f'{BASE}/files' and got['list_key'] == 'files' and got['max_pages'] == 1


# --- cli -----------------------------------------------------------------


def _fake(monkeypatch, *, mime='application/pdf', next_token=None):
    calls = []

    def fake_paginate(base, endpoint, token, params, max_pages=None, debug=False):
        calls.append(('list', params, max_pages))
        return [{'id': 'f1', 'name': 'a', 'mimeType': 'application/pdf', 'size': '3'}], next_token

    def fake_get(base, endpoint, token, params=None, debug=False):
        calls.append(('get', endpoint, params))
        if endpoint == 'about':
            return {'user': {'displayName': 'Me', 'emailAddress': 'me@x'}}
        return {'id': 'f1', 'name': 'a', 'mimeType': mime}

    def fake_bytes(base, endpoint, token, params=None, debug=False):
        calls.append(('bytes', endpoint, params))
        return b'DATA'

    monkeypatch.setattr(cli.api_mod, 'paginate', fake_paginate)
    monkeypatch.setattr(cli.api_mod, 'api_get', fake_get)
    monkeypatch.setattr(cli.api_mod, 'api_get_bytes', fake_bytes)
    return calls


def test_bare_ls_lists_root_folders_first(monkeypatch, capsys):
    calls = _fake(monkeypatch)
    assert cli.cmd_ls([], {}, 'tok', BASE) == 0
    out = capsys.readouterr()
    assert out.err == '' and json.loads(out.out)[0]['id'] == 'f1'
    params = calls[0][1]
    assert "'root' in parents" in params['q'] and params['orderBy'] == 'folder,name_natural'
    assert calls[0][2] == 1


def test_name_search_covers_whole_drive_and_fulltext_drops_order(monkeypatch, capsys):
    calls = _fake(monkeypatch, next_token='more')
    assert cli.cmd_ls(['--name', 'budget'], {}, 'tok', BASE) == 0
    assert "in parents" not in calls[0][1]['q'] and calls[0][1]['orderBy'] == 'modifiedTime desc'
    assert json.loads(capsys.readouterr().out)['next_page_token'] == 'more'
    calls = _fake(monkeypatch)
    assert cli.cmd_ls(['--search', 'x', '--all', '--pretty'], {}, 'tok', BASE) == 0
    assert 'orderBy' not in calls[0][1] and calls[0][2] is None
    assert 'a' in capsys.readouterr().out


@pytest.mark.parametrize('args, match', [
    (['--type', 'blob'], 'file or folder'), (['--max-results', '0'], 'between'),
    (['--max-results', 'x'], 'integer'), (['--bogus'], 'Unknown flag'), (['a', 'b'], 'Unexpected'),
])
def test_ls_usage_errors(args, match):
    with pytest.raises(UsageError, match=match):
        cli.cmd_ls(args, {}, 'tok', BASE)


def test_show_json_and_pretty(monkeypatch, capsys):
    _fake(monkeypatch)
    assert cli.cmd_show(['f1'], {}, 'tok', BASE) == 0
    assert json.loads(capsys.readouterr().out)['id'] == 'f1'
    assert cli.cmd_show(['f1', '--pretty'], {}, 'tok', BASE) == 0
    assert 'Name:     a' in capsys.readouterr().out
    with pytest.raises(UsageError, match='file id'):
        cli.cmd_show([], {}, 'tok', BASE)


def test_get_regular_file_uses_alt_media(monkeypatch, tmp_path, capsys):
    calls = _fake(monkeypatch)
    out = tmp_path / 'a.pdf'
    assert cli.cmd_get(['f1', '--out', str(out)], {}, 'tok', BASE) == 0
    assert out.read_bytes() == b'DATA' and calls[-1] == ('bytes', 'files/f1', {'alt': 'media'})
    with pytest.raises(ConflictError):
        cli.cmd_get(['f1', '--out', str(out)], {}, 'tok', BASE)
    assert cli.cmd_get(['f1'], {}, 'tok', BASE) == 0  # stdout bytes


def test_get_google_doc_exports(monkeypatch, tmp_path, capsys):
    calls = _fake(monkeypatch, mime=DOC_MIME)
    out = tmp_path / 'a.pdf'
    assert cli.cmd_get(['f1', '--out', str(out), '--export-mime', 'application/pdf'], {}, 'tok', BASE) == 0
    assert calls[-1] == ('bytes', 'files/f1/export', {'mimeType': 'application/pdf'})
    assert 'exported as application/pdf' in capsys.readouterr().err


@pytest.mark.parametrize('mime, match', [
    (files.FOLDER_MIME, 'is a folder'), ('application/vnd.google-apps.form', 'export-mime'),
])
def test_get_undownloadable_is_usage_error(monkeypatch, mime, match):
    _fake(monkeypatch, mime=mime)
    with pytest.raises(UsageError, match=match):
        cli.cmd_get(['f1'], {}, 'tok', BASE)


def test_format_helpers():
    assert format.format_files_pretty([]) == '(no files)'
    assert format._size(None) == '-' and format._size(512) == '512B' and format._size(2048) == '2.0K'
    assert format._size(5 * 1024 ** 3) == '5.0G'


def test_main_schema_version_and_errors(capsys):
    assert cli._main(['schema']) == 0
    names = {r['name'] for r in json.loads(capsys.readouterr().out)['commands']}
    assert names == {'ls', 'show', 'get', 'refresh', 'config'}
    assert cli.main(['--version']) == 0
    assert capsys.readouterr().out.startswith('owa-gdrive ')
    assert cli.main(['nope']) == 2
    assert cli.main([]) == 0


def test_main_dispatch_alias_refresh_config(monkeypatch, capsys):
    seen = {}
    monkeypatch.setattr(cli.config_mod, 'load_config', lambda: {})
    monkeypatch.setattr(cli.config_mod, 'config_set', lambda k, v: seen.update({k: v}))
    monkeypatch.setattr(cli.auth_mod, 'setup_auth', lambda config, debug=False: (seen.update(cfg=dict(config)) or 'tok', BASE))
    _fake(monkeypatch)
    assert cli._main(['list', '--profile', 'g1', '--debug']) == 0
    assert seen['cfg'] == {'owa_piggy_profile': 'g1', 'debug': True}
    assert cli._main(['refresh']) == 0
    assert 'Authenticated as Me <me@x>' in capsys.readouterr().err
    assert cli._main(['config', '--profile', 'g2']) == 0 and seen['owa_piggy_profile'] == 'g2'
    assert cli._main(['config']) == 0


# --- auth ------------------------------------------------------------------


def test_setup_auth(monkeypatch):
    monkeypatch.setattr(auth, 'get_token', lambda **kw: BrokerToken('opaque', 'gdrive'))
    assert auth.setup_auth({'owa_piggy_profile': 'g1'}) == ('opaque', auth.API_BASE)

    def unknown(**kw):
        raise AuthExpiredError("unknown audience 'gdrive'")

    monkeypatch.setattr(auth, 'get_token', unknown)
    with pytest.raises(UsageError, match='not a Google profile'):
        auth.setup_auth({'owa_piggy_profile': 'nc'})

    def expired(**kw):
        raise AuthExpiredError('invalid_grant')

    monkeypatch.setattr(auth, 'get_token', expired)
    with pytest.raises(AuthExpiredError):
        auth.setup_auth({'owa_piggy_profile': 'g1'})
