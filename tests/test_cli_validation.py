"""Tests for CLI input validation: invalid numeric input must produce
an `ERROR:` stderr line and exit non-zero, never a bare traceback.
Also covers the empty-PATCH guard in cmd_update and the JSON-by-default
contract in cmd_categories.
"""
import json

import pytest


def test_events_limit_non_integer_exits_clean(capsys):
    from owa_cal.cli import cmd_events
    with pytest.raises(SystemExit) as exc:
        cmd_events(['--limit', 'nope'], {}, 'tok', 'https://example.invalid')
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert 'ERROR:' in err
    assert 'integer' in err.lower()


def test_events_week_non_integer_exits_clean(capsys):
    from owa_cal.cli import cmd_events
    with pytest.raises(SystemExit) as exc:
        cmd_events(['--week', 'nope'], {}, 'tok', 'https://example.invalid')
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert 'ERROR:' in err


def test_update_without_fields_returns_error(capsys, monkeypatch):
    """Regression for the empty-PATCH bug: `owa-cal update --id X`
    with no other flags must fail fast, not send a `{}` PATCH."""
    from owa_cal.cli import cmd_update
    # Sentinel to catch any API call attempt
    def boom(*args, **kwargs):
        raise AssertionError('no API call should happen')
    import owa_cal.api as api_mod
    monkeypatch.setattr(api_mod, 'api_request', boom)
    rc = cmd_update(['--id', 'abc'], {}, 'tok', 'https://example.invalid')
    assert rc == 1
    err = capsys.readouterr().err
    assert 'at least one field' in err


def test_create_allday_uses_midnight_next_day(capsys, monkeypatch):
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
            'IsAllDay': body['IsAllDay'],
        }

    monkeypatch.setattr(api_mod, 'api_request', fake_request)
    monkeypatch.setattr(api_mod, 'api_get', lambda *a, **k: {'value': []})

    rc = cmd_create(
        ['--subject', 'Holiday', '--date', '2026-04-20', '--allday'],
        {'default_timezone': 'W. Europe Standard Time'},
        'tok',
        'https://example.invalid',
    )

    assert rc == 0
    assert captured['body']['Start']['DateTime'] == '2026-04-20T00:00:00'
    assert captured['body']['End']['DateTime'] == '2026-04-21T00:00:00'
    assert captured['body']['IsAllDay'] is True
    capsys.readouterr()


def test_update_end_time_preserves_existing_end_date(monkeypatch, force_tz):
    from owa_cal.cli import cmd_update
    import owa_cal.api as api_mod

    force_tz('UTC')
    captured = {}

    def fake_get(base, endpoint, token, debug=False):
        captured['get_endpoint'] = endpoint
        return {
            'Id': 'a/b',
            'Subject': 'Overnight',
            'Start': {'DateTime': '2026-04-20T22:00:00', 'TimeZone': 'UTC'},
            'End': {'DateTime': '2026-04-21T01:00:00', 'TimeZone': 'UTC'},
        }

    def fake_request(method, base, endpoint, token, body=None, debug=False):
        captured['request_endpoint'] = endpoint
        captured['body'] = body
        return {
            'Id': 'a/b',
            'Subject': 'Overnight',
            'Start': {'DateTime': '2026-04-20T22:00:00', 'TimeZone': 'UTC'},
            'End': body['End'],
        }

    monkeypatch.setattr(api_mod, 'api_get', fake_get)
    monkeypatch.setattr(api_mod, 'api_request', fake_request)

    rc = cmd_update(
        ['--id', 'a/b', '--end', '02:00'],
        {'default_timezone': 'UTC'},
        'tok',
        'https://example.invalid',
    )

    assert rc == 0
    assert captured['get_endpoint'] == 'me/events/a%2Fb'
    assert captured['request_endpoint'] == 'me/events/a%2Fb'
    assert captured['body']['End']['DateTime'] == '2026-04-21T02:00:00'


def test_update_date_preserves_all_day_end_delta(monkeypatch, force_tz):
    from owa_cal.cli import cmd_update
    import owa_cal.api as api_mod

    force_tz('UTC')
    captured = {}

    def fake_get(base, endpoint, token, debug=False):
        return {
            'Id': 'evt-1',
            'Subject': 'Holiday',
            'Start': {'DateTime': '2026-04-20T00:00:00', 'TimeZone': 'UTC'},
            'End': {'DateTime': '2026-04-21T00:00:00', 'TimeZone': 'UTC'},
            'IsAllDay': True,
        }

    def fake_request(method, base, endpoint, token, body=None, debug=False):
        captured['body'] = body
        return {
            'Id': 'evt-1',
            'Subject': 'Holiday',
            'Start': body['Start'],
            'End': body['End'],
            'IsAllDay': True,
        }

    monkeypatch.setattr(api_mod, 'api_get', fake_get)
    monkeypatch.setattr(api_mod, 'api_request', fake_request)

    rc = cmd_update(
        ['--id', 'evt-1', '--date', '2026-04-22'],
        {'default_timezone': 'UTC'},
        'tok',
        'https://example.invalid',
    )

    assert rc == 0
    assert captured['body']['Start']['DateTime'] == '2026-04-22T00:00:00'
    assert captured['body']['End']['DateTime'] == '2026-04-23T00:00:00'


def test_events_search_uses_calendar_view_range_and_filters(capsys, monkeypatch):
    from owa_cal.cli import cmd_events
    import owa_cal.api as api_mod

    captured = {}

    def fake_get(base, endpoint, token, debug=False):
        captured['endpoint'] = endpoint
        return {'value': [
            {
                'Id': '1',
                'Subject': 'Daily standup',
                'Start': {'DateTime': '2026-04-20T09:00:00', 'TimeZone': 'UTC'},
                'End': {'DateTime': '2026-04-20T09:30:00', 'TimeZone': 'UTC'},
            },
            {
                'Id': '2',
                'Subject': 'Lunch',
                'Start': {'DateTime': '2026-04-20T11:00:00', 'TimeZone': 'UTC'},
                'End': {'DateTime': '2026-04-20T11:30:00', 'TimeZone': 'UTC'},
            },
        ]}

    monkeypatch.setattr(api_mod, 'api_get', fake_get)

    rc = cmd_events(
        ['--date', '2026-04-20', '--search', 'standup'],
        {},
        'tok',
        'https://example.invalid',
    )

    assert rc == 0
    assert captured['endpoint'].startswith('me/calendarView?')
    assert 'startDateTime=2026-04-20T00%3A00%3A00' in captured['endpoint']
    parsed = json.loads(capsys.readouterr().out)
    assert [event['subject'] for event in parsed] == ['Daily standup']


def test_refresh_returns_error_when_verify_fails(capsys, monkeypatch):
    from owa_cal.cli import cmd_refresh
    import owa_cal.api as api_mod
    import owa_cal.auth as auth_mod

    monkeypatch.setattr(auth_mod, 'do_token_refresh', lambda config, debug=False: 'tok')
    monkeypatch.setattr(api_mod, 'api_get', lambda *a, **k: None)

    rc = cmd_refresh([], {})

    assert rc == 1
    assert 'Auth verification failed' in capsys.readouterr().err


def test_categories_json_by_default(capsys, monkeypatch):
    """Regression for the JSON-contract bug: `owa-cal categories` must
    emit JSON on stdout, not an aligned text table."""
    from owa_cal.cli import cmd_categories
    import owa_cal.api as api_mod
    def fake_get(base, endpoint, token, debug=False):
        return {'value': [
            {'DisplayName': 'Alpha', 'Color': 'Preset0'},
            {'DisplayName': 'Beta', 'Color': 'Preset1'},
        ]}
    monkeypatch.setattr(api_mod, 'api_get', fake_get)
    rc = cmd_categories([], {}, 'tok', 'https://example.invalid')
    assert rc == 0
    stdout = capsys.readouterr().out
    parsed = json.loads(stdout)
    assert parsed == [
        {'name': 'Alpha', 'color': 'Preset0'},
        {'name': 'Beta', 'color': 'Preset1'},
    ]


def test_categories_pretty_opt_in(capsys, monkeypatch):
    from owa_cal.cli import cmd_categories
    import owa_cal.api as api_mod
    def fake_get(base, endpoint, token, debug=False):
        return {'value': [{'DisplayName': 'Alpha', 'Color': 'Preset0'}]}
    monkeypatch.setattr(api_mod, 'api_get', fake_get)
    rc = cmd_categories(['--pretty'], {}, 'tok', 'https://example.invalid')
    assert rc == 0
    out = capsys.readouterr().out
    # No JSON brackets, should have the category name
    assert 'Alpha' in out
    assert 'Preset0' in out
    assert '[' not in out
