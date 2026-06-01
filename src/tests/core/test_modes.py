import json
import os

from owa_core import modes
from owa_core.errors import AuthExpiredError, UsageError, emit_error


def test_agent_mode_wraps_json_stdout(capsys):
    def dispatch(argv):
        assert argv == ['messages']
        print('[{"id":"1"}]')
        return 0

    rc = modes.run_with_output_modes('owa-mail', ['--agent', 'messages'], dispatch)

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload['_owa']['suite'] == 'owa-tools'
    assert payload['_owa']['tool'] == 'owa-mail'
    assert payload['_owa']['command'] == 'messages'
    assert payload['data'] == [{'id': '1'}]


def test_agent_mode_can_be_enabled_by_env(monkeypatch, capsys):
    monkeypatch.setenv('OWA_AGENT', '1')

    rc = modes.run_with_output_modes('owa-people', ['me'], lambda _argv: print('{"id":"me"}') or 0)

    assert rc == 0
    assert json.loads(capsys.readouterr().out)['data'] == {'id': 'me'}


def test_agent_mode_rejects_non_json_stdout(capsys):
    rc = modes.run_with_output_modes(
        'owa-mail',
        ['--agent', 'messages', '--pretty'],
        lambda _argv: print('human table') or 0,
    )

    captured = capsys.readouterr()
    assert rc == 2
    assert captured.out == 'human table\n'
    assert 'requires JSON stdout' in captured.err


def test_agent_mode_replays_stdout_on_nonzero_return(capsys):
    rc = modes.run_with_output_modes(
        'owa-doctor',
        ['--agent', 'probe'],
        lambda _argv: print('{"health":"failed"}') or 2,
    )

    assert rc == 2
    assert capsys.readouterr().out == '{"health":"failed"}\n'


def test_agent_mode_handles_empty_success_output(capsys):
    rc = modes.run_with_output_modes('owa-mail', ['--agent'], lambda _argv: 0)

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload['_owa']['tool'] == 'owa-mail'
    assert 'command' not in payload['_owa']
    assert payload['data'] is None


def test_agent_mode_catches_system_exit(capsys):
    def dispatch(_argv):
        print('{"ok":true}')
        raise SystemExit(0)

    rc = modes.run_with_output_modes('owa-mail', ['--agent', 'config'], dispatch)

    assert rc == 0
    assert json.loads(capsys.readouterr().out)['data'] == {'ok': True}


def test_non_agent_mode_catches_system_exit():
    def dispatch(_argv):
        raise SystemExit(7)

    assert modes.run_with_output_modes('owa-mail', ['config'], dispatch) == 7


def test_non_agent_mode_renders_owa_error(capsys):
    def dispatch(_argv):
        raise AuthExpiredError('token expired')

    rc = modes.run_with_output_modes('owa-mail', ['messages'], dispatch)

    assert rc == 11
    assert 'token expired' in capsys.readouterr().err


def test_agent_mode_rejects_binary_stdout_without_out(capsys):
    rc = modes.run_with_output_modes(
        'owa-drive',
        ['--agent', 'get', '/Report.pdf'],
        lambda _argv: 0,
        binary_stdout_commands=('get',),
    )

    captured = capsys.readouterr()
    assert rc == 2
    assert captured.out == ''
    assert 'write binary output with --out' in captured.err


def test_agent_mode_refuses_interactive_command(capsys):
    launched = []
    rc = modes.run_with_output_modes(
        'owa-mail',
        ['--agent', 'tui'],
        lambda _argv: launched.append(True) or 0,
        interactive_commands=('tui',),
    )

    captured = capsys.readouterr()
    assert rc == 2
    # Refused before the dispatcher runs (so before auth/launch).
    assert launched == []
    assert captured.out == ''
    assert 'interactive terminal' in captured.err
    assert 'cannot run under' in captured.err


def test_agent_env_refuses_interactive_command(monkeypatch, capsys):
    monkeypatch.setenv('OWA_AGENT', '1')
    launched = []
    rc = modes.run_with_output_modes(
        'owa-mail',
        ['tui'],
        lambda _argv: launched.append(True) or 0,
        interactive_commands=('tui',),
    )

    assert rc == 2
    assert launched == []
    assert 'interactive terminal' in capsys.readouterr().err


def test_interactive_command_runs_without_agent():
    launched = []
    rc = modes.run_with_output_modes(
        'owa-mail',
        ['tui'],
        lambda _argv: launched.append(True) or 0,
        interactive_commands=('tui',),
    )
    assert rc == 0
    assert launched == [True]


def test_err_json_mode_formats_emitted_errors(capsys):
    def dispatch(_argv):
        return emit_error(AuthExpiredError('token expired'), tool='owa-mail', command='messages')

    rc = modes.run_with_output_modes('owa-mail', ['--err-json', 'messages'], dispatch)

    captured = capsys.readouterr()
    assert rc == 11
    assert captured.out == ''
    payload = json.loads(captured.err)
    assert payload['error']['code'] == 'AUTH_EXPIRED'
    assert payload['error']['tool'] == 'owa-mail'
    assert payload['error']['command'] == 'messages'
    assert payload['error']['exit_code'] == 11


def test_err_json_can_include_hint_and_env_context(monkeypatch, capsys):
    monkeypatch.setenv('OWA_ERR_JSON', '1')
    monkeypatch.setenv('OWA_TOOL', 'owa-cal')
    monkeypatch.setenv('OWA_COMMAND', 'events')

    rc = emit_error(UsageError('bad input', remediation='try --help'))

    payload = json.loads(capsys.readouterr().err)
    assert rc == 2
    assert payload['error']['hint'] == 'try --help'
    assert payload['error']['tool'] == 'owa-cal'
    assert payload['error']['command'] == 'events'


def test_command_name_stops_at_double_dash():
    assert modes.command_name(['--', 'messages']) == ''


def test_envelope_includes_profile_from_env(monkeypatch):
    monkeypatch.setenv('OWA_PROFILE', 'work')

    payload = modes.envelope('owa-mail', 'messages', [])

    assert payload['_owa']['profile'] == 'work'


def test_doctor_invocation_only_matches_top_level_flags():
    assert modes.is_doctor_invocation(['--doctor'])
    assert modes.is_doctor_invocation(['--doctor', '--json'])
    assert modes.is_doctor_invocation(['--json', '--doctor'])
    assert not modes.is_doctor_invocation(['GET', '/me', '--header', '--doctor'])
    assert not modes.is_doctor_invocation(['--doctor', '--pretty'])


def test_doctor_value_position_reaches_dispatch():
    seen = {}

    def dispatch(argv):
        seen['argv'] = argv
        return 7

    rc = modes.run_with_output_modes(
        'owa-graph',
        ['GET', '/me', '--header', '--doctor'],
        dispatch,
    )

    assert rc == 7
    assert seen['argv'] == ['GET', '/me', '--header', '--doctor']


def test_mode_environment_is_restored(monkeypatch):
    monkeypatch.setenv('OWA_TOOL', 'before')
    monkeypatch.delenv('OWA_ERR_JSON_ACTIVE', raising=False)

    modes.run_with_output_modes('owa-mail', ['--err-json', 'messages'], lambda _argv: 0)

    assert os.environ['OWA_TOOL'] == 'before'
    assert 'OWA_ERR_JSON_ACTIVE' not in os.environ
