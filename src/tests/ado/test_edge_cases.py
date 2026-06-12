"""Edge-case coverage: bad-input normalizers, config round-trip, api branches."""
from owa_ado import api as api_mod
from owa_ado import config as config_mod
from owa_ado import resources as res
from owa_core.errors import OwaError
from owa_core.http import Response


def test_normalizers_return_empty_for_non_dict():
    for fn in (res.normalize_project, res.normalize_iteration,
               res.normalize_work_item, res.normalize_repo,
               res.normalize_pr, res.normalize_pipeline, res.normalize_build):
        assert fn(None) == {}
        assert fn('not-a-dict') == {}


def test_identity_falls_back_to_id():
    out = res.normalize_work_item({'id': 1, 'fields': {'System.AssignedTo': {'id': 'guid'}}})
    assert out['assignedTo'] == 'guid'


def test_build_wiql_iteration_clause():
    q = res.build_wiql(iteration='NOCOS\\CD 1')
    assert "[System.IterationPath] = 'NOCOS\\CD 1'" in q


def test_config_round_trip(tmp_config):
    config_mod.save_config({'ado_org': 'Org', 'ado_project': 'Proj'})
    loaded = config_mod.load_config()
    assert loaded['ado_org'] == 'Org'
    config_mod.config_set('owa_piggy_profile', 'work')
    assert config_mod.load_config()['owa_piggy_profile'] == 'work'


def test_parse_kv_stream_filters_to_allowlist():
    out = config_mod.parse_kv_stream('ado_org="X"\nbogus="Y"\n')
    assert out == {'ado_org': 'X'}


def test_ado_request_generic_owaerror_maps_to_none(monkeypatch):
    monkeypatch.setattr(api_mod.http, 'request',
                        lambda *a, **k: (_ for _ in ()).throw(OwaError('weird')))
    assert api_mod.ado_request('GET', 'https://x', 'a', 'tok') is None


def test_ado_paginate_non_list_payload_returns_single(monkeypatch):
    monkeypatch.setattr(api_mod.http, 'request',
                        lambda *a, **k: Response(status=200, headers={},
                                                 json={'count': 0}, bytes=b''))
    assert api_mod.ado_paginate('https://x', 'a', 'tok') == [{'count': 0}]


def test_ado_paginate_generic_owaerror_maps_to_none(monkeypatch):
    monkeypatch.setattr(api_mod.http, 'request',
                        lambda *a, **k: (_ for _ in ()).throw(OwaError('weird')))
    assert api_mod.ado_paginate('https://x', 'a', 'tok') is None


def test_json_patch_debug_logs(monkeypatch, capsys):
    monkeypatch.setattr(api_mod.http, 'request',
                        lambda *a, **k: Response(status=200, headers={}, json={'id': 1}, bytes=b''))
    api_mod.json_patch('POST', 'https://x', 'a', 'tok',
                       operations=[{'op': 'add', 'path': '/f', 'value': 1}], debug=True)
    assert 'json-patch' in capsys.readouterr().err
