"""owa-halo: normalizers, CLI and auth. No network, no real tokens."""
import json

import pytest

from owa_core.auth import BrokerProfile, BrokerToken
from owa_core.errors import AuthExpiredError, ConflictError, UsageError
from owa_halo import auth, cli, ticket

BASE = 'https://acme.haloitsm.com'
IMG = 'https://acme.haloitsm.com/api/attachment/image?token=' + 'f' * 24  # built so the scanner skips it


def _payloads():
    return {
        'ticket': {
            'id': 7, 'summary': 'Printer', 'status_id': 9, 'user_name': 'Ada', 'details': None,
            'details_html': f'<p>see</p><img src="{IMG}">', 'customfields': [], 'onhold': False,
        },
        'actions': {'record_count': 2, 'actions': [
            {'id': 2, 'datetime': '2026-01-02', 'who': 'Bob', 'new_status_name': 'Closed',
             'note_html': 'done &amp; dusted'},
            {'id': 1, 'datetime': '2026-01-01', 'who': 'Ada', 'note_html': f'<img src="{IMG}">'},
        ]},
        'attachments': {'attachments': [{'id': 5, 'filename': 'log.txt', 'filesize': 3, 's3url': 'x'}]},
        'statuses': [{'id': 9, 'name': 'Closed'}],
    }


def _fake_api(monkeypatch, payloads=None, blobs=None):
    p = payloads or _payloads()
    calls = []
    monkeypatch.setattr(cli.api_mod, 'get_ticket', lambda b, t, i, debug=False: p['ticket'])

    def get_actions(b, t, i, include_system=False, debug=False):
        calls.append(('actions', include_system))
        return p['actions']

    monkeypatch.setattr(cli.api_mod, 'get_actions', get_actions)
    monkeypatch.setattr(cli.api_mod, 'get_attachments', lambda b, t, i, debug=False: p['attachments'])
    monkeypatch.setattr(cli.api_mod, 'get_statuses', lambda b, t, debug=False: p['statuses'])
    monkeypatch.setattr(cli.api_mod, 'attachment_link', lambda b, t, i, debug=False: f'https://cdn/{i}')
    blobs = blobs or {IMG: b'\x89PNG\r\n\x1a\nxx', 'https://cdn/5': b'log'}
    monkeypatch.setattr(cli.api_mod, 'fetch_unauthenticated', lambda url, debug=False: blobs[url])
    return calls


@pytest.mark.parametrize('ref, expected', [
    ('69296', (69296, None)),
    ('https://acme.haloitsm.com/ticket?id=12', (12, 'acme.haloitsm.com')),
])
def test_parse_ticket_ref(ref, expected):
    assert ticket.parse_ticket_ref(ref) == expected


def test_parse_ticket_ref_rejects_garbage():
    with pytest.raises(UsageError):
        ticket.parse_ticket_ref('https://acme.haloitsm.com/ticket')


def test_build_ticket_compacts_names_status_and_hides_image_urls():
    p = _payloads()
    out, images = ticket.build_ticket(p['ticket'], p['actions'], p['attachments'], p['statuses'], base=BASE)
    assert out['status'] == {'id': 9, 'name': 'Closed'}
    assert out['url'] == f'{BASE}/ticket?id=7'
    assert 'details' not in out['ticket'] and 'customfields' not in out['ticket']
    assert out['ticket']['onhold'] is False
    # The same image in body and creation action is one image.
    assert [i['url'] for i in images] == [IMG]
    assert out['images'] == [{'n': 1, 'source': 'ticket'}]
    assert out['attachments'] == [{'id': 5, 'filename': 'log.txt', 'filesize': 3}]
    assert 'token=' not in json.dumps(out)
    assert 'halo-image:1' in out['actions'][1]['note_html']


def test_format_ticket_is_chronological_plain_text():
    p = _payloads()
    out, _ = ticket.build_ticket(p['ticket'], p['actions'], p['attachments'], p['statuses'], base=BASE)
    text = ticket.format_ticket(out)
    assert text.index('Ada') < text.index('Bob -> Closed')
    assert 'done & dusted' in text and '[image 1]' in text
    assert 'attachments: 1, inline images: 1' in text


def test_cmd_ticket_json(monkeypatch, capsys):
    calls = _fake_api(monkeypatch)
    assert cli.cmd_ticket(['7', '--all'], {}, 'tok', BASE) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)['summary'] == 'Printer'
    assert captured.err == ''
    assert calls == [('actions', True)]


def test_cmd_ticket_pretty_and_truncation_warning(monkeypatch, capsys):
    p = _payloads()
    p['actions']['record_count'] = 50
    _fake_api(monkeypatch, p)
    assert cli.cmd_ticket(['7', '--pretty'], {}, 'tok', BASE) == 0
    captured = capsys.readouterr()
    assert captured.out.startswith('#7 Printer')
    assert 'returned 2 of 50 actions' in captured.err


def test_cmd_ticket_rejects_other_host():
    with pytest.raises(UsageError, match='other.haloitsm.com'):
        cli.cmd_ticket(['https://other.haloitsm.com/ticket?id=1'], {}, 'tok', BASE)


@pytest.mark.parametrize('args, match', [
    ([], 'required'), (['1', '2'], 'Unexpected'), (['1', '--nope'], 'Unknown flag'),
    (['1', '--out', 'x'], 'Unknown flag'),
])
def test_cmd_ticket_usage_errors(args, match):
    with pytest.raises(UsageError, match=match):
        cli.cmd_ticket(args, {}, 'tok', BASE)


def test_cmd_attachments_lists_without_downloading(monkeypatch, capsys):
    _fake_api(monkeypatch, blobs={})
    assert cli.cmd_attachments(['7'], {}, 'tok', BASE) == 0
    rows = json.loads(capsys.readouterr().out)
    assert [(r['kind'], 'path' in r) for r in rows] == [('attachment', False), ('image', False)]


def test_cmd_attachments_downloads_and_never_overwrites(monkeypatch, capsys, tmp_path):
    _fake_api(monkeypatch)
    assert cli.cmd_attachments(['7', '--out', str(tmp_path), '--pretty'], {}, 'tok', BASE) == 0
    assert (tmp_path / '7-5-log.txt').read_bytes() == b'log'
    assert (tmp_path / '7-image-1.png').exists()
    assert 'inline image 1 (ticket)' in capsys.readouterr().out
    with pytest.raises(ConflictError):
        cli.cmd_attachments(['7', '--out', str(tmp_path)], {}, 'tok', BASE)


def test_main_schema_and_version(capsys):
    assert cli._main(['schema']) == 0
    names = {row['name'] for row in json.loads(capsys.readouterr().out)['commands']}
    assert names == {'ticket', 'attachments'}
    assert cli._main(['--version']) == 0
    assert capsys.readouterr().out.startswith('owa-halo ')


def test_main_unknown_command_and_missing_ref_before_auth(monkeypatch):
    monkeypatch.setattr(cli.auth_mod, 'setup_auth', lambda *a, **k: pytest.fail('authed'))
    with pytest.raises(UsageError, match='Unknown command'):
        cli._main(['nope'])
    with pytest.raises(UsageError, match='required'):
        cli._main(['ticket'])


def test_main_applies_profile_and_dispatches(monkeypatch, capsys):
    seen = {}

    def fake_setup(config, debug=False):
        seen.update(config)
        return 'tok', BASE

    monkeypatch.setattr(cli.auth_mod, 'setup_auth', fake_setup)
    _fake_api(monkeypatch)
    assert cli._main(['ticket', '7', '-p', 'h1', '--debug']) == 0
    assert seen == {'owa_piggy_profile': 'h1', 'debug': True}


def test_main_exit_codes(capsys):
    assert cli.main(['nope']) == 2
    assert cli.main([]) == 0


def _profiles(monkeypatch, rows):
    monkeypatch.setattr(auth, 'get_profiles', lambda **kw: rows)


def test_resolve_profile(monkeypatch):
    nc = BrokerProfile('nc', False, True, True, services=('owa', 'ado', 'halo'))
    swon = BrokerProfile('swon', True, True, True)
    assert auth.resolve_profile({'owa_piggy_profile': 'x'}) == 'x'
    _profiles(monkeypatch, [swon, nc])
    assert auth.resolve_profile({}) == 'nc'
    _profiles(monkeypatch, [swon])
    with pytest.raises(UsageError, match='clients add halo='):
        auth.resolve_profile({})
    other = BrokerProfile('h2', False, True, True, services=('halo',))
    _profiles(monkeypatch, [nc, other])
    with pytest.raises(UsageError, match='nc, h2'):
        auth.resolve_profile({})
    # The default profile wins when it has Halo.
    _profiles(monkeypatch, [BrokerProfile('nc', True, True, True, services=('owa', 'halo')), other])
    assert auth.resolve_profile({}) == 'nc'


def test_broker_rows_without_services_derive_them_from_type(monkeypatch):
    from owa_core import auth as core_auth

    class _Proc:
        returncode = 0
        stderr = ''
        stdout = json.dumps({'profiles': [
            {'alias': 'old-halo', 'type': 'halo', 'has_config': True},
            {'alias': 'nc', 'services': ['owa', 'halo'], 'edge_dir': '/x/nc/edge-profile'},
        ]})

    monkeypatch.setattr(core_auth, '_ensure_broker_available', lambda *a: None)
    monkeypatch.setattr(core_auth.subprocess, 'run', lambda *a, **kw: _Proc())
    old, nc = core_auth.get_profiles(tool_name='owa-halo')
    assert old.services == ('halo',)
    assert (nc.services, nc.edge_dir) == (('owa', 'halo'), '/x/nc/edge-profile')


def test_setup_auth_uses_broker_host(monkeypatch):
    token = BrokerToken(access_token='opaque', audience='halo', raw={'host': 'acme.haloitsm.com'})
    monkeypatch.setattr(auth, 'get_token', lambda **kw: token)
    assert auth.setup_auth({'owa_piggy_profile': 'h1'}) == ('opaque', BASE)
    monkeypatch.setattr(auth, 'get_token', lambda **kw: BrokerToken('opaque', 'halo', raw={}))
    with pytest.raises(UsageError, match='no Halo sign-in'):
        auth.setup_auth({'owa_piggy_profile': 'h1'})


def test_setup_auth_maps_unknown_audience(monkeypatch):
    def boom(**kw):
        raise AuthExpiredError("ERROR: unknown audience 'halo'")

    monkeypatch.setattr(auth, 'get_token', boom)
    with pytest.raises(UsageError, match="'nc' has no Halo sign-in"):
        auth.setup_auth({'owa_piggy_profile': 'nc'})

    def expired(**kw):
        raise AuthExpiredError('invalid_grant')

    monkeypatch.setattr(auth, 'get_token', expired)
    with pytest.raises(AuthExpiredError):
        auth.setup_auth({'owa_piggy_profile': 'nc'})


def test_api_builds_urls_and_keeps_bearer_off_cdn(monkeypatch):
    from types import SimpleNamespace

    from owa_halo import api

    seen = []
    monkeypatch.setattr(api.http, 'request', lambda m, url, token, debug=False: (
        seen.append((url, token)) or SimpleNamespace(json={'link': 'https://cdn/x'})))
    monkeypatch.setattr(api.http, 'request_unauthenticated', lambda m, url, debug=False: (
        seen.append((url, None)) or SimpleNamespace(bytes=b'z')))
    api.get_ticket(BASE, 't', 7)
    api.get_actions(BASE, 't', 7)
    api.get_actions(BASE, 't', 7, include_system=True)
    api.get_attachments(BASE, 't', 7)
    api.get_statuses(BASE, 't')
    assert api.attachment_link(BASE, 't', 5) == 'https://cdn/x'
    assert api.fetch_unauthenticated('https://cdn/x') == b'z'
    urls = [u for u, _ in seen]
    assert urls[0] == f'{BASE}/api/Tickets/7?includedetails=true'
    assert 'excludesys=true' in urls[1] and 'excludesys' not in urls[2]
    assert urls[3] == f'{BASE}/api/Attachment?ticket_id=7'
    assert urls[4] == f'{BASE}/api/Status'
    assert urls[5] == f'{BASE}/api/Attachment/5'
    assert seen[-1] == ('https://cdn/x', None)
