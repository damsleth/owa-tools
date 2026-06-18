"""Additional CLI coverage for owa_cal.cli paths not exercised by existing test files.

Targets:
- print_help / help / --version entry points (_main lines 1071-1078)
- _command_name returning '' (line 93)
- _split_datetime no-T path (line 65)
- _date_delta_days missing values (line 76)
- _require_value raises UsageError (line 242)
- cmd_events_webcal --limit, --all, --from, --to, --pretty, debug, unknown flag
- cmd_events --from/--to/--all, --pretty, debug print, all_pages path, api returns None
- cmd_create --showas flag, api POST returns None
- cmd_update --category/--location/--body/--showas, positional id, date-only shift,
  existing GET returns None, PATCH returns None
- cmd_delete unknown flag, GET returns None, DELETE returns None
- cmd_categories: api_get returns None, api_request add returns falsy
- cmd_config: unknown flag, no-profile-set message
- cmd_refresh: unknown flag, auth verification fails
- _main: help/--help/-h/--version flags, --profile missing value,
  empty after stripping globals, subcommand help, unknown command,
  webcal events dispatch, profiles/refresh/config dispatch, all authed commands
- _format_profiles_pretty: no local profiles (only piggy), empty listing
- _profiles_list: unknown flag
- _profiles_add: extra unexpected argument, unknown flag
- _profiles_delete: flag-that-starts-with-dash, extra unexpected arg, no alias
- cmd_profiles: unknown sub
"""
import json

import pytest

import owa_cal.api as api_mod
import owa_cal.auth as auth_mod
from owa_cal import cli
from owa_cal.cli import (
    UsageError,
    _command_name,
    _date_delta_days,
    _split_datetime,
    cmd_categories,
    cmd_config,
    cmd_create,
    cmd_delete,
    cmd_events,
    cmd_events_webcal,
    cmd_refresh,
    cmd_update,
    print_help,
)

# ---------------------------------------------------------------------------
# Tiny helpers
# ---------------------------------------------------------------------------

def _raw_event(eid='e1', subject='Standup',
               start='2026-04-20T09:00:00', end='2026-04-20T09:30:00',
               tz='UTC'):
    return {
        'Id': eid, 'Subject': subject,
        'Start': {'DateTime': start, 'TimeZone': tz},
        'End': {'DateTime': end, 'TimeZone': tz},
        'Categories': [], 'Location': {}, 'ShowAs': 'Busy', 'IsAllDay': False,
    }


@pytest.fixture(autouse=True)
def _default_stubs(monkeypatch):
    monkeypatch.setattr(cli.config_mod, 'load_config', lambda: {'default_timezone': 'UTC'})
    monkeypatch.setattr(cli.auth_mod, 'setup_auth',
                        lambda config, debug=False: ('tok', 'https://outlook.test'))


# ---------------------------------------------------------------------------
# Tiny pure-function coverage
# ---------------------------------------------------------------------------

def test_split_datetime_no_T():
    assert _split_datetime('2026-04-20') == ('', '')


def test_split_datetime_empty():
    assert _split_datetime('') == ('', '')


def test_split_datetime_with_T():
    result = _split_datetime('2026-04-20T09:00:00')
    assert result[0] == '2026-04-20'
    assert result[1] == '09:00:00'


def test_date_delta_days_missing_start():
    assert _date_delta_days('', '2026-04-20') == 0


def test_date_delta_days_missing_end():
    assert _date_delta_days('2026-04-20', '') == 0


def test_date_delta_days_both_present():
    assert _date_delta_days('2026-04-20', '2026-04-22') == 2


def test_command_name_empty_argv():
    assert _command_name([]) == ''


def test_command_name_skips_debug_verbose():
    assert _command_name(['--debug', '--verbose', 'events']) == 'events'


def test_command_name_skips_profile():
    assert _command_name(['--profile', 'work', 'events']) == 'events'


def test_command_name_only_global_flags_returns_empty():
    assert _command_name(['--debug', '--profile', 'work']) == ''


# ---------------------------------------------------------------------------
# _require_value raises UsageError when args is empty
# ---------------------------------------------------------------------------

def test_require_value_raises_on_empty():
    from owa_cal.cli import _require_value
    with pytest.raises(UsageError, match='--date requires a value'):
        _require_value('--date', [])


# ---------------------------------------------------------------------------
# print_help runs without error
# ---------------------------------------------------------------------------

def test_print_help_runs(capsys):
    print_help()
    out = capsys.readouterr().out
    assert 'owa-cal' in out
    assert 'events' in out


# ---------------------------------------------------------------------------
# _main: help / --help / -h / --version
# ---------------------------------------------------------------------------

def test_main_no_args_prints_help(capsys):
    rc = cli._main([])
    assert rc == 0
    assert 'owa-cal' in capsys.readouterr().out


def test_main_help_flag(capsys):
    rc = cli._main(['help'])
    assert rc == 0
    assert 'owa-cal' in capsys.readouterr().out


def test_main_dash_help_flag(capsys):
    rc = cli._main(['--help'])
    assert rc == 0
    capsys.readouterr()


def test_main_h_flag(capsys):
    rc = cli._main(['-h'])
    assert rc == 0
    capsys.readouterr()


def test_main_version_flag(capsys):
    rc = cli._main(['--version'])
    assert rc == 0
    out = capsys.readouterr().out
    assert 'owa-cal' in out


def test_main_v_flag(capsys):
    rc = cli._main(['-v'])
    assert rc == 0
    capsys.readouterr()


# ---------------------------------------------------------------------------
# _main: --profile missing value
# ---------------------------------------------------------------------------

def test_main_profile_requires_value():
    with pytest.raises(UsageError, match='--profile requires a value'):
        cli._main(['--profile'])


# ---------------------------------------------------------------------------
# _main: empty argv after stripping global flags
# ---------------------------------------------------------------------------

def test_main_empty_after_global_flags(capsys):
    rc = cli._main(['--debug'])
    assert rc == 0
    capsys.readouterr()


# ---------------------------------------------------------------------------
# _main: unknown command raises UsageError
# ---------------------------------------------------------------------------

def test_main_unknown_command():
    with pytest.raises(UsageError, match='Unknown command'):
        cli._main(['boguscommand'])


# ---------------------------------------------------------------------------
# _main dispatches refresh/config/profiles without auth
# ---------------------------------------------------------------------------

def test_main_dispatches_refresh(monkeypatch, capsys):
    monkeypatch.setattr(cli.auth_mod, 'do_token_refresh', lambda c, debug=False: 'tok')
    monkeypatch.setattr(cli.api_mod, 'api_get',
                        lambda *a, **k: {'DisplayName': 'Test User'})
    rc = cli._main(['refresh'])
    assert rc == 0
    assert 'Test User' in capsys.readouterr().err


def test_main_dispatches_config(monkeypatch, capsys):
    saved = {}
    monkeypatch.setattr(cli.config_mod, 'CONFIG_PATH', '/tmp/owa-cal-cfg-test')
    monkeypatch.setattr(cli.config_mod, 'config_set',
                        lambda k, v: saved.setdefault(k, v))
    rc = cli._main(['config', '--profile', 'myprofile'])
    assert rc == 0
    assert saved.get('owa_piggy_profile') == 'myprofile'


def test_main_dispatches_profiles(monkeypatch, capsys):
    monkeypatch.setattr(cli.profiles_mod, 'load_local', lambda: {})
    monkeypatch.setattr(cli.profiles_mod, 'piggy_aliases', lambda: (set(), ''))
    rc = cli._main(['profiles'])
    assert rc == 0
    rows = json.loads(capsys.readouterr().out)
    assert rows == []


# ---------------------------------------------------------------------------
# _main dispatches all authed commands (events/create/update/delete/respond/categories)
# ---------------------------------------------------------------------------

def test_main_dispatches_events(monkeypatch, capsys):
    monkeypatch.setattr(cli.api_mod, 'api_get',
                        lambda *a, **k: {'value': [_raw_event()]})
    rc = cli._main(['events', '--date', '2026-04-20'])
    assert rc == 0
    rows = json.loads(capsys.readouterr().out)
    assert rows[0]['subject'] == 'Standup'


def test_main_dispatches_create(monkeypatch, capsys):
    monkeypatch.setattr(cli.api_mod, 'api_request',
                        lambda *a, **k: _raw_event('new', 'MyMeeting'))
    monkeypatch.setattr(cli.api_mod, 'api_get', lambda *a, **k: {'value': []})
    rc = cli._main(['create', '--subject', 'MyMeeting'])
    assert rc == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed['subject'] == 'MyMeeting'


def test_main_dispatches_update(monkeypatch, capsys):
    monkeypatch.setattr(cli.api_mod, 'api_request',
                        lambda *a, **k: _raw_event('e1', 'Updated'))
    rc = cli._main(['update', '--id', 'e1', '--subject', 'Updated'])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)['subject'] == 'Updated'


def test_main_dispatches_delete(monkeypatch, capsys):
    monkeypatch.setattr(cli.api_mod, 'api_request', lambda *a, **k: {})
    rc = cli._main(['delete', '--id', 'e1', '--confirm'])
    assert rc == 0
    assert 'Deleted' in capsys.readouterr().err


def test_main_dispatches_respond(monkeypatch, capsys):
    monkeypatch.setattr(cli.api_mod, 'api_request', lambda *a, **k: {})
    rc = cli._main(['respond', '--id', 'e1', '--action', 'accept'])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)['action'] == 'accept'


def test_main_dispatches_categories(monkeypatch, capsys):
    monkeypatch.setattr(cli.api_mod, 'api_get',
                        lambda *a, **k: {'value': [{'DisplayName': 'Blue', 'Color': 'Preset0'}]})
    rc = cli._main(['categories'])
    assert rc == 0
    rows = json.loads(capsys.readouterr().out)
    assert rows[0]['name'] == 'Blue'


# ---------------------------------------------------------------------------
# _main: webcal events dispatch
# ---------------------------------------------------------------------------

def test_main_webcal_events_dispatched(monkeypatch, capsys):
    monkeypatch.setattr(cli.profiles_mod, 'load_local',
                        lambda: {'feed': {'webcal_url': 'https://feed.test/ical'}})
    monkeypatch.setattr(cli.profiles_mod, 'piggy_aliases', lambda: (set(), ''))
    monkeypatch.setattr(cli.config_mod, 'load_config',
                        lambda: {'owa_piggy_profile': 'feed'})
    monkeypatch.setattr(cli.ics_mod, 'fetch_and_normalize',
                        lambda url: [{'id': '1', 'subject': 'Test', 'start': '2026-04-20T09:00:00',
                                      'end': '2026-04-20T10:00:00', 'categories': [],
                                      'location': '', 'showAs': '', 'isAllDay': False, 'body': ''}])
    rc = cli._main(['events', '--date', '2026-04-20'])
    assert rc == 0
    rows = json.loads(capsys.readouterr().out)
    assert rows[0]['subject'] == 'Test'


# ---------------------------------------------------------------------------
# cmd_events_webcal: --limit, --all no-op, --from/--to, --pretty, debug, unknown flag
# ---------------------------------------------------------------------------

def test_cmd_events_webcal_limit(monkeypatch, capsys):
    monkeypatch.setattr(cli.ics_mod, 'fetch_and_normalize', lambda url: [
        {'id': str(i), 'subject': f'E{i}', 'start': f'2026-04-{20+i:02d}T09:00:00',
         'end': f'2026-04-{20+i:02d}T10:00:00', 'categories': [], 'location': '',
         'showAs': '', 'isAllDay': False, 'body': ''}
        for i in range(5)
    ])
    rc = cmd_events_webcal(['--limit', '2', '--from', '2026-04-01', '--to', '2026-04-30'],
                           {'webcal_url': 'x'})
    assert rc == 0
    rows = json.loads(capsys.readouterr().out)
    assert len(rows) == 2


def test_cmd_events_webcal_all_flag_noop(monkeypatch, capsys):
    monkeypatch.setattr(cli.ics_mod, 'fetch_and_normalize', lambda url: [])
    rc = cmd_events_webcal(['--all', '--from', '2026-04-01', '--to', '2026-04-30'],
                           {'webcal_url': 'x'})
    assert rc == 0
    capsys.readouterr()


def test_cmd_events_webcal_pretty(monkeypatch, capsys):
    monkeypatch.setattr(cli.ics_mod, 'fetch_and_normalize', lambda url: [
        {'id': '1', 'subject': 'Pretty', 'start': '2026-04-20T09:00:00',
         'end': '2026-04-20T10:00:00', 'categories': [], 'location': '',
         'showAs': '', 'isAllDay': False, 'body': ''}
    ])
    rc = cmd_events_webcal(['--pretty', '--date', '2026-04-20'], {'webcal_url': 'x'})
    assert rc == 0
    out = capsys.readouterr().out
    assert 'Pretty' in out


def test_cmd_events_webcal_unknown_flag():
    with pytest.raises(UsageError, match='Unknown flag'):
        cmd_events_webcal(['--bogus'], {'webcal_url': 'x'})


def test_cmd_events_webcal_debug_prints_to_stderr(monkeypatch, capsys):
    monkeypatch.setattr(cli.ics_mod, 'fetch_and_normalize', lambda url: [])
    rc = cmd_events_webcal(['--from', '2026-04-01', '--to', '2026-04-30'],
                           {'webcal_url': 'https://x.test', 'debug': True})
    assert rc == 0
    assert 'DEBUG' in capsys.readouterr().err


# ---------------------------------------------------------------------------
# cmd_events: --from/--to/--all (paginate), --pretty, debug, api returns None
# ---------------------------------------------------------------------------

def test_cmd_events_from_to_flags(monkeypatch, capsys):
    captured = {}

    def fake_get(base, endpoint, token, debug=False):
        captured['endpoint'] = endpoint
        return {'value': []}

    monkeypatch.setattr(api_mod, 'api_get', fake_get)
    rc = cmd_events(['--from', '2026-04-01', '--to', '2026-04-30'],
                    {}, 'tok', 'https://outlook.test')
    assert rc == 0
    assert '2026-04-01' in captured['endpoint']
    capsys.readouterr()


def test_cmd_events_pretty_output(monkeypatch, capsys):
    monkeypatch.setattr(api_mod, 'api_get',
                        lambda *a, **k: {'value': [_raw_event()]})
    rc = cmd_events(['--pretty', '--date', '2026-04-20'],
                    {}, 'tok', 'https://outlook.test')
    assert rc == 0
    out = capsys.readouterr().out
    assert 'Standup' in out


def test_cmd_events_all_pages(monkeypatch, capsys):
    monkeypatch.setattr(api_mod, 'paginate_all',
                        lambda base, url, token, debug=False: [_raw_event()])
    rc = cmd_events(['--all', '--date', '2026-04-20'],
                    {}, 'tok', 'https://outlook.test')
    assert rc == 0
    rows = json.loads(capsys.readouterr().out)
    assert len(rows) == 1


def test_cmd_events_all_pages_returns_none(monkeypatch, capsys):
    monkeypatch.setattr(api_mod, 'paginate_all',
                        lambda *a, **k: None)
    rc = cmd_events(['--all', '--date', '2026-04-20'],
                    {}, 'tok', 'https://outlook.test')
    assert rc == 1
    capsys.readouterr()


def test_cmd_events_api_get_returns_none(monkeypatch):
    monkeypatch.setattr(api_mod, 'api_get', lambda *a, **k: None)
    rc = cmd_events(['--date', '2026-04-20'], {}, 'tok', 'https://outlook.test')
    assert rc == 1


def test_cmd_events_debug_mode(monkeypatch, capsys):
    monkeypatch.setattr(api_mod, 'api_get', lambda *a, **k: {'value': []})
    rc = cmd_events(['--date', '2026-04-20'], {'debug': True}, 'tok', 'https://outlook.test')
    assert rc == 0
    assert 'DEBUG' in capsys.readouterr().err


# ---------------------------------------------------------------------------
# cmd_create: --showas flag, api POST returns None
# ---------------------------------------------------------------------------

def test_cmd_create_showas_flag(monkeypatch, capsys):
    captured = {}

    def fake_request(method, base, endpoint, token, body=None, debug=False):
        captured['body'] = body
        return _raw_event('new', 'Meeting')

    monkeypatch.setattr(api_mod, 'api_request', fake_request)
    monkeypatch.setattr(api_mod, 'api_get', lambda *a, **k: {'value': []})

    rc = cmd_create(['--subject', 'Meeting', '--showas', 'Free'],
                    {}, 'tok', 'https://outlook.test')
    assert rc == 0
    assert captured['body']['ShowAs'] == 'Free'
    capsys.readouterr()


def test_cmd_create_api_returns_none(monkeypatch):
    monkeypatch.setattr(api_mod, 'api_request', lambda *a, **k: None)
    rc = cmd_create(['--subject', 'Meeting'], {}, 'tok', 'https://outlook.test')
    assert rc == 1


# ---------------------------------------------------------------------------
# cmd_update: --category/--location/--body/--showas fields, date-only shift,
#             positional id, existing GET returns None, PATCH returns None
# ---------------------------------------------------------------------------

def test_cmd_update_category_location_body_showas(monkeypatch, capsys):
    captured = {}

    def fake_request(method, base, endpoint, token, body=None, debug=False):
        captured['body'] = body
        return _raw_event('e1', 'Updated')

    monkeypatch.setattr(api_mod, 'api_request', fake_request)

    rc = cmd_update(
        ['--id', 'e1', '--category', 'Cat', '--location', 'Loc',
         '--body', 'notes', '--showas', 'Free'],
        {}, 'tok', 'https://outlook.test',
    )
    assert rc == 0
    body = captured['body']
    assert body.get('Categories') == ['Cat']
    assert body.get('Location') == {'DisplayName': 'Loc'}
    assert body.get('Body') == {'ContentType': 'Text', 'Content': 'notes'}
    assert body.get('ShowAs') == 'Free'
    capsys.readouterr()


def test_cmd_update_date_only_shifts_both_times(monkeypatch, capsys):
    """--date alone shifts start+end to the new date, preserving times."""

    def fake_get(base, endpoint, token, debug=False):
        return _raw_event('e1', 'Meeting',
                          start='2026-04-20T09:00:00', end='2026-04-20T10:00:00')

    captured = {}

    def fake_request(method, base, endpoint, token, body=None, debug=False):
        captured['body'] = body
        return _raw_event('e1', 'Meeting')

    monkeypatch.setattr(api_mod, 'api_get', fake_get)
    monkeypatch.setattr(api_mod, 'api_request', fake_request)

    rc = cmd_update(['--id', 'e1', '--date', '2026-04-22'],
                    {}, 'tok', 'https://outlook.test')
    assert rc == 0
    body = captured['body']
    assert '2026-04-22' in body['Start']['DateTime']
    assert '2026-04-22' in body['End']['DateTime']
    capsys.readouterr()


def test_cmd_update_positional_id(monkeypatch, capsys):
    monkeypatch.setattr(api_mod, 'api_request',
                        lambda *a, **k: _raw_event('e1', 'Pos'))
    rc = cmd_update(['e1', '--subject', 'Pos'], {}, 'tok', 'https://outlook.test')
    assert rc == 0
    capsys.readouterr()


def test_cmd_update_get_returns_none_when_date_given(monkeypatch):
    monkeypatch.setattr(api_mod, 'api_get', lambda *a, **k: None)
    rc = cmd_update(['--id', 'e1', '--date', '2026-04-22'],
                    {}, 'tok', 'https://outlook.test')
    assert rc == 1


def test_cmd_update_patch_returns_none(monkeypatch):
    monkeypatch.setattr(api_mod, 'api_request', lambda *a, **k: None)
    rc = cmd_update(['--id', 'e1', '--subject', 'X'],
                    {}, 'tok', 'https://outlook.test')
    assert rc == 1


# ---------------------------------------------------------------------------
# cmd_delete: unknown flag, GET returns None, DELETE returns None
# ---------------------------------------------------------------------------

def test_cmd_delete_unknown_flag():
    with pytest.raises(UsageError, match='Unknown flag'):
        cmd_delete(['--id', 'e1', '--bogus'], {}, 'tok', 'https://outlook.test')


def test_cmd_delete_get_returns_none(monkeypatch, capsys):
    monkeypatch.setattr(cli.tty_mod, 'require_confirm_or_tty', lambda action: None)
    monkeypatch.setattr(api_mod, 'api_get', lambda *a, **k: None)
    rc = cmd_delete(['--id', 'e1'], {}, 'tok', 'https://outlook.test')
    assert rc == 1
    capsys.readouterr()


def test_cmd_delete_delete_returns_none(monkeypatch, capsys):
    monkeypatch.setattr(api_mod, 'api_request', lambda *a, **k: None)
    rc = cmd_delete(['--id', 'e1', '--confirm'], {}, 'tok', 'https://outlook.test')
    assert rc == 1
    capsys.readouterr()


# ---------------------------------------------------------------------------
# cmd_categories: api_get returns None, api_request add returns falsy
# ---------------------------------------------------------------------------

def test_cmd_categories_api_get_none(monkeypatch):
    monkeypatch.setattr(api_mod, 'api_get', lambda *a, **k: None)
    rc = cmd_categories([], {}, 'tok', 'https://outlook.test')
    assert rc == 1


def test_cmd_categories_add_returns_none(monkeypatch, capsys):
    monkeypatch.setattr(api_mod, 'api_request', lambda *a, **k: None)
    rc = cmd_categories(['--add', 'Red'], {}, 'tok', 'https://outlook.test')
    assert rc == 1
    capsys.readouterr()


def test_cmd_categories_unknown_flag():
    with pytest.raises(UsageError, match='Unknown flag'):
        cmd_categories(['--bogus'], {}, 'tok', 'https://outlook.test')


# ---------------------------------------------------------------------------
# cmd_config: unknown flag, no-profile-set message
# ---------------------------------------------------------------------------

def test_cmd_config_unknown_flag():
    with pytest.raises(UsageError, match='Unknown flag'):
        cmd_config(['--bogus'], {})


def test_cmd_config_no_profile_set_message(tmp_config, capsys):
    rc = cmd_config([], {})
    assert rc == 0
    err = capsys.readouterr().err
    assert 'not set' in err


# ---------------------------------------------------------------------------
# cmd_refresh: unknown flag raises, auth verification returns non-dict
# ---------------------------------------------------------------------------

def test_cmd_refresh_unknown_flag():
    with pytest.raises(UsageError, match='Unknown flag'):
        cmd_refresh(['--bogus'], {})


def test_cmd_refresh_auth_verification_fails(monkeypatch, capsys):
    monkeypatch.setattr(auth_mod, 'do_token_refresh', lambda c, debug=False: 'tok')
    monkeypatch.setattr(api_mod, 'api_get', lambda *a, **k: 'not-a-dict')
    rc = cmd_refresh([], {})
    assert rc == 1
    assert 'verification failed' in capsys.readouterr().err


# ---------------------------------------------------------------------------
# _format_profiles_pretty: no local profiles, empty listing
# ---------------------------------------------------------------------------

def test_format_profiles_pretty_no_local_only_piggy():
    from owa_cal.cli import _format_profiles_pretty
    result = _format_profiles_pretty({}, {'work', 'home'}, 'work')
    assert 'owa-piggy (oauth)' in result
    assert '* work' in result
    assert 'home' in result


def test_format_profiles_pretty_empty():
    from owa_cal.cli import _format_profiles_pretty
    result = _format_profiles_pretty({}, set(), '')
    assert result == 'No profiles configured.'


def test_format_profiles_pretty_shadow_marker():
    from owa_cal.cli import _format_profiles_pretty
    result = _format_profiles_pretty({'feed': {'webcal_url': 'x'}}, {'feed'}, '')
    assert 'also defined in owa-piggy' in result
    assert 'shadowed by owa-cal' in result


# ---------------------------------------------------------------------------
# _profiles_list: unknown flag
# ---------------------------------------------------------------------------

def test_profiles_list_unknown_flag(monkeypatch):
    monkeypatch.setattr(cli.profiles_mod, 'load_local', lambda: {})
    monkeypatch.setattr(cli.profiles_mod, 'piggy_aliases', lambda: (set(), ''))
    with pytest.raises(UsageError, match='Unknown flag'):
        cli._profiles_list(['--bogus'])


# ---------------------------------------------------------------------------
# _profiles_add: extra unexpected argument, unknown flag
# ---------------------------------------------------------------------------

def test_profiles_add_unexpected_extra_arg():
    with pytest.raises(UsageError, match='Unexpected argument'):
        cli._profiles_add(['alias1', 'unexpected'])


def test_profiles_add_unknown_flag():
    with pytest.raises(UsageError, match='Unknown flag'):
        cli._profiles_add(['--bogus'])


# ---------------------------------------------------------------------------
# _profiles_delete: flag starting with dash, extra unexpected arg, no alias
# ---------------------------------------------------------------------------

def test_profiles_delete_flag_raises():
    with pytest.raises(UsageError, match='Unknown flag'):
        cli._profiles_delete(['--bogus'])


def test_profiles_delete_extra_arg_raises():
    with pytest.raises(UsageError, match='Unexpected argument'):
        cli._profiles_delete(['alias', 'extra'])


def test_profiles_delete_no_alias(capsys):
    rc = cli._profiles_delete([])
    assert rc == 1
    assert 'requires' in capsys.readouterr().err


# ---------------------------------------------------------------------------
# cmd_profiles: unknown subcommand
# ---------------------------------------------------------------------------

def test_cmd_profiles_unknown_sub(capsys):
    rc = cli.cmd_profiles(['bogus'], {})
    assert rc == 1
    assert 'Unknown subcommand' in capsys.readouterr().err
