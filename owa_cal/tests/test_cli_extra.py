"""Tests covering CLI surface that the smoke/validation files don't hit:
delete confirmation, config writes for --app-client-id, the --week
range computation, the post-create duplicate warning, and the
categories --add POST shape.
"""
import json

import pytest


def test_config_app_client_id_persists(tmp_config, clean_env):
    from owa_cal.cli import cmd_config
    cmd_config(['--app-client-id', 'cid-123'], {})
    assert 'OUTLOOK_APP_CLIENT_ID="cid-123"' in tmp_config.read_text()


def test_config_no_args_lists_state_to_stderr(tmp_config, clean_env, capsys):
    from owa_cal.cli import cmd_config
    cmd_config([], {'default_timezone': 'UTC', 'owa_piggy_profile': 'work'})
    err = capsys.readouterr().err
    assert 'Config file:' in err
    assert 'owa_piggy_profile=work' in err
    assert 'default_timezone=UTC' in err


def test_delete_no_confirm_aborts_on_n(monkeypatch, capsys):
    from owa_cal.cli import cmd_delete
    import owa_cal.api as api_mod

    api_calls = []

    def fake_get(base, endpoint, token, debug=False):
        api_calls.append(('GET', endpoint))
        return {
            'Id': 'evt-1',
            'Subject': 'Standup',
            'Start': {'DateTime': '2026-04-20T09:00:00', 'TimeZone': 'UTC'},
            'End': {'DateTime': '2026-04-20T09:30:00', 'TimeZone': 'UTC'},
        }

    def fake_request(method, *args, **kwargs):
        api_calls.append((method, 'request'))
        return {}

    monkeypatch.setattr(api_mod, 'api_get', fake_get)
    monkeypatch.setattr(api_mod, 'api_request', fake_request)
    monkeypatch.setattr('builtins.input', lambda: 'n')

    rc = cmd_delete(['--id', 'evt-1'], {}, 'tok', 'https://example.invalid')
    assert rc == 0
    # No DELETE was issued
    assert all(call[0] != 'DELETE' for call in api_calls)
    err = capsys.readouterr().err
    assert 'Aborted' in err


def test_delete_with_confirm_skips_prompt(monkeypatch, capsys):
    from owa_cal.cli import cmd_delete
    import owa_cal.api as api_mod

    captured = {}

    def fake_request(method, base, endpoint, token, body=None, debug=False):
        captured['method'] = method
        captured['endpoint'] = endpoint
        return {}

    def fake_get(*a, **k):
        raise AssertionError('--confirm should skip the pre-fetch GET')

    monkeypatch.setattr(api_mod, 'api_request', fake_request)
    monkeypatch.setattr(api_mod, 'api_get', fake_get)
    monkeypatch.setattr(
        'builtins.input',
        lambda: (_ for _ in ()).throw(AssertionError('no prompt expected')),
    )

    rc = cmd_delete(
        ['--id', 'a/b', '--confirm'], {}, 'tok', 'https://example.invalid',
    )
    assert rc == 0
    assert captured['method'] == 'DELETE'
    assert captured['endpoint'] == 'me/events/a%2Fb'


def test_events_week_range_query(monkeypatch, capsys):
    from owa_cal.cli import cmd_events
    import owa_cal.api as api_mod

    captured = {}

    def fake_get(base, endpoint, token, debug=False):
        captured['endpoint'] = endpoint
        return {'value': []}

    monkeypatch.setattr(api_mod, 'api_get', fake_get)

    rc = cmd_events(
        ['--week', '16', '--year', '2026'], {}, 'tok', 'https://example.invalid',
    )
    assert rc == 0
    # ISO week 16 of 2026: Mon 2026-04-13 .. Sun 2026-04-19
    assert 'startDateTime=2026-04-13T00%3A00%3A00' in captured['endpoint']
    assert 'endDateTime=2026-04-19T23%3A59%3A59' in captured['endpoint']
    capsys.readouterr()


def test_create_uses_default_timezone_from_config(monkeypatch, capsys):
    from owa_cal.cli import cmd_create
    import owa_cal.api as api_mod

    captured = {}

    def fake_request(method, base, endpoint, token, body=None, debug=False):
        captured['body'] = body
        return {
            'Id': 'evt-1',
            'Subject': body['Subject'],
            'Start': body['Start'],
            'End': body['End'],
        }

    monkeypatch.setattr(api_mod, 'api_request', fake_request)
    monkeypatch.setattr(api_mod, 'api_get', lambda *a, **k: {'value': []})

    rc = cmd_create(
        ['--subject', 'Lunsj', '--date', '2026-04-20',
         '--start', '11:00', '--end', '11:30'],
        {'default_timezone': 'UTC'},
        'tok',
        'https://example.invalid',
    )
    assert rc == 0
    assert captured['body']['Start']['TimeZone'] == 'UTC'
    assert captured['body']['End']['TimeZone'] == 'UTC'
    capsys.readouterr()


def test_create_warns_on_duplicate(monkeypatch, capsys):
    """Post-create dupe check: if another event with the same
    subject+start+end exists for that day, we warn on stderr without
    failing the command. Anchors the warning surface."""
    from owa_cal.cli import cmd_create
    import owa_cal.api as api_mod

    new_event = {
        'Id': 'evt-new',
        'Subject': 'Lunsj',
        'Start': {'DateTime': '2026-04-20T11:00:00', 'TimeZone': 'UTC'},
        'End': {'DateTime': '2026-04-20T11:30:00', 'TimeZone': 'UTC'},
    }
    existing = {'value': [
        {
            'Id': 'evt-old',
            'Subject': 'Lunsj',
            'Start': {'DateTime': '2026-04-20T11:00:00', 'TimeZone': 'UTC'},
            'End': {'DateTime': '2026-04-20T11:30:00', 'TimeZone': 'UTC'},
        },
        new_event,
    ]}

    monkeypatch.setattr(api_mod, 'api_request',
                        lambda *a, **k: new_event)
    monkeypatch.setattr(api_mod, 'api_get', lambda *a, **k: existing)

    rc = cmd_create(
        ['--subject', 'Lunsj', '--date', '2026-04-20',
         '--start', '11:00', '--end', '11:30'],
        {'default_timezone': 'UTC'},
        'tok',
        'https://example.invalid',
    )
    assert rc == 0
    captured = capsys.readouterr()
    assert 'duplicates' in captured.err.lower()
    # stdout still contains the JSON record (jq contract preserved)
    parsed = json.loads(captured.out)
    assert parsed['id'] == 'evt-new'


def test_categories_add_posts_correct_body(monkeypatch, capsys):
    from owa_cal.cli import cmd_categories
    import owa_cal.api as api_mod

    captured = {}

    def fake_request(method, base, endpoint, token, body=None, debug=False):
        captured['method'] = method
        captured['endpoint'] = endpoint
        captured['body'] = body
        return {'DisplayName': body['DisplayName'], 'Color': body['Color']}

    monkeypatch.setattr(api_mod, 'api_request', fake_request)
    rc = cmd_categories(
        ['--add', 'Project Z'], {}, 'tok', 'https://example.invalid',
    )
    assert rc == 0
    assert captured['method'] == 'POST'
    assert captured['endpoint'] == 'me/MasterCategories'
    assert captured['body'] == {'DisplayName': 'Project Z', 'Color': 'Preset0'}
    parsed = json.loads(capsys.readouterr().out)
    assert parsed['DisplayName'] == 'Project Z'


def test_refresh_happy_path_prints_display_name(monkeypatch, capsys):
    from owa_cal.cli import cmd_refresh
    import owa_cal.api as api_mod
    import owa_cal.auth as auth_mod

    monkeypatch.setattr(auth_mod, 'do_token_refresh', lambda c, debug=False: 'tok')
    monkeypatch.setattr(
        api_mod, 'api_get',
        lambda base, endpoint, token, debug=False: {'DisplayName': 'Ada Lovelace'},
    )

    rc = cmd_refresh([], {})
    assert rc == 0
    err = capsys.readouterr().err
    assert 'Ada Lovelace' in err


def test_refresh_failure_returns_error(monkeypatch, capsys):
    from owa_cal.cli import cmd_refresh
    import owa_cal.auth as auth_mod

    monkeypatch.setattr(auth_mod, 'do_token_refresh', lambda c, debug=False: None)
    rc = cmd_refresh([], {})
    assert rc == 1
    assert 'Token refresh failed' in capsys.readouterr().err


def test_unknown_flag_on_events_exits_clean(capsys):
    from owa_cal.cli import cmd_events
    with pytest.raises(SystemExit) as exc:
        cmd_events(['--bogus'], {}, 'tok', 'https://example.invalid')
    assert exc.value.code == 1
    assert 'Unknown flag' in capsys.readouterr().err
