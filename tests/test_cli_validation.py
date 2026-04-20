"""Tests for CLI input validation: invalid numeric input must produce
an `ERROR:` stderr line and exit non-zero, never a bare traceback.
Also covers the empty-PATCH guard in cmd_update and the JSON-by-default
contract in cmd_categories.
"""
import json

import pytest


def test_events_limit_non_integer_exits_clean(capsys):
    from cal_cli.cli import cmd_events
    with pytest.raises(SystemExit) as exc:
        cmd_events(['--limit', 'nope'], {}, 'tok', 'https://example.invalid', 'pascal')
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert 'ERROR:' in err
    assert 'integer' in err.lower()


def test_events_week_non_integer_exits_clean(capsys):
    from cal_cli.cli import cmd_events
    with pytest.raises(SystemExit) as exc:
        cmd_events(['--week', 'nope'], {}, 'tok', 'https://example.invalid', 'pascal')
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert 'ERROR:' in err


def test_update_without_fields_returns_error(capsys, monkeypatch):
    """Regression for the empty-PATCH bug: `cal-cli update --id X`
    with no other flags must fail fast, not send a `{}` PATCH."""
    from cal_cli.cli import cmd_update
    # Sentinel to catch any API call attempt
    def boom(*args, **kwargs):
        raise AssertionError('no API call should happen')
    import cal_cli.api as api_mod
    monkeypatch.setattr(api_mod, 'api_request', boom)
    rc = cmd_update(['--id', 'abc'], {}, 'tok', 'https://example.invalid', 'pascal')
    assert rc == 1
    err = capsys.readouterr().err
    assert 'at least one field' in err


def test_categories_json_by_default(capsys, monkeypatch):
    """Regression for the JSON-contract bug: `cal-cli categories` must
    emit JSON on stdout, not an aligned text table."""
    from cal_cli.cli import cmd_categories
    import cal_cli.api as api_mod
    def fake_get(base, endpoint, token, debug=False):
        return {'value': [
            {'DisplayName': 'Alpha', 'Color': 'Preset0'},
            {'DisplayName': 'Beta', 'Color': 'Preset1'},
        ]}
    monkeypatch.setattr(api_mod, 'api_get', fake_get)
    rc = cmd_categories([], {}, 'tok', 'https://example.invalid', 'pascal')
    assert rc == 0
    stdout = capsys.readouterr().out
    parsed = json.loads(stdout)
    assert parsed == [
        {'name': 'Alpha', 'color': 'Preset0'},
        {'name': 'Beta', 'color': 'Preset1'},
    ]


def test_categories_pretty_opt_in(capsys, monkeypatch):
    from cal_cli.cli import cmd_categories
    import cal_cli.api as api_mod
    def fake_get(base, endpoint, token, debug=False):
        return {'value': [{'DisplayName': 'Alpha', 'Color': 'Preset0'}]}
    monkeypatch.setattr(api_mod, 'api_get', fake_get)
    rc = cmd_categories(['--pretty'], {}, 'tok', 'https://example.invalid', 'pascal')
    assert rc == 0
    out = capsys.readouterr().out
    # No JSON brackets, should have the category name
    assert 'Alpha' in out
    assert 'Preset0' in out
    assert '[' not in out
