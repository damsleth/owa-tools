import json

import pytest

from owa_places import cli

BASE = 'https://outlook.test'


def test_rooms_filters_and_prints_json(monkeypatch, capsys):
    def fake_post(base, token, body=None, cv='', debug=False):
        assert base == BASE
        assert token == 'tok'
        assert body == {'NumberOfLocations': 25}
        return {
            'Locations': [
                {'DisplayName': 'Room A', 'EmailAddress': 'room-a@example.com'},
                {'DisplayName': 'Cafe'},
            ]
        }

    monkeypatch.setattr(cli.api_mod, 'scheduling_post', fake_post)
    assert cli.cmd_rooms(['--query', 'room'], {}, 'tok', BASE) == 0
    rows = json.loads(capsys.readouterr().out)
    assert [row['name'] for row in rows] == ['Room A']


def test_locations_pretty(monkeypatch, capsys):
    monkeypatch.setattr(
        cli.api_mod,
        'scheduling_post',
        lambda *args, **kwargs: {'Locations': [{'DisplayName': 'Room A', 'EmailAddress': 'room-a@example.com'}]},
    )
    assert cli.cmd_locations(['--pretty'], {}, 'tok', BASE) == 0
    assert 'Room A' in capsys.readouterr().out


def test_unknown_flag_rejected():
    with pytest.raises(cli.UsageError, match='Unknown flag'):
        cli.cmd_locations(['--nope'], {}, 'tok', BASE)


def test_main_schema(capsys):
    assert cli._main(['schema']) == 0
    payload = json.loads(capsys.readouterr().out)
    assert {row['name'] for row in payload['commands']} >= {'rooms', 'locations', 'recent'}


@pytest.mark.parametrize('argv', [
    ['rooms', '--profile', 'crayon'],
    ['--profile', 'crayon', 'rooms'],
    ['rooms', '-p', 'crayon'],
])
def test_main_strips_and_applies_profile(monkeypatch, capsys, argv):
    seen = {}

    def fake_setup_auth(config, debug=False):
        seen['profile'] = config.get('owa_piggy_profile')
        return 'tok', BASE

    monkeypatch.setattr(cli.config_mod, 'load_config', lambda: {})
    monkeypatch.setattr(cli.auth_mod, 'setup_auth', fake_setup_auth)
    monkeypatch.setattr(cli.api_mod, 'scheduling_post', lambda *a, **k: {'Locations': []})
    assert cli._main(argv) == 0
    assert seen['profile'] == 'crayon'
