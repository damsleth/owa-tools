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


# --- multi-profile fan-out ---------------------------------------------------


def test_single_profile_passes_filtered_argv_untouched(capsys):
    seen = []

    def dispatch(argv):
        seen.append(argv)
        print('{"id":"1"}')
        return 0

    modes.run_with_output_modes('owa-mail', ['--profile', 'x', 'messages'], dispatch)
    capsys.readouterr()
    modes.run_with_output_modes('owa-mail', ['messages'], dispatch)
    capsys.readouterr()

    # N<=1 passes the ORIGINAL filtered argv through untouched (the single
    # --profile is NOT stripped by the fan-out path; the tool's _main owns it).
    assert seen[0] == ['--profile', 'x', 'messages']
    assert seen[1] == ['messages']


def test_single_profile_agent_output_byte_identical(capsys):
    # The fan-out path is a no-op for N<=1: a single-profile agent run must
    # produce the exact same envelope+wrapping the pre-change single-run code
    # produced for the same argv. We prove that by running the same dispatch
    # under fan_out_profiles=True (default) and fan_out_profiles=False (which
    # bypasses parse_profiles entirely, i.e. the original code path).
    def dispatch(_argv):
        print('{"id":"1"}')
        return 0

    argv = ['--agent', '--profile', 'x', 'messages']

    modes.run_with_output_modes('owa-mail', argv, dispatch)
    with_fan_out = capsys.readouterr().out

    modes.run_with_output_modes('owa-mail', argv, dispatch, fan_out_profiles=False)
    without_fan_out = capsys.readouterr().out

    assert with_fan_out == without_fan_out


def test_multi_profile_json_merge(capsys):
    def dispatch(argv):
        # Last token is the appended profile value.
        print('{"id":"' + argv[-1] + '"}')
        return 0

    rc = modes.run_with_output_modes('owa-mail', ['--profile', 'a', '--profile', 'b', 'messages'], dispatch)

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload['_owa']['suite'] == 'owa-tools'
    assert payload['_owa']['tool'] == 'owa-mail'
    assert payload['_owa']['command'] == 'messages'
    assert payload['_owa']['profiles'] == ['a', 'b']
    results = payload['results']
    assert [r['profile'] for r in results] == ['a', 'b']
    assert all(r['ok'] for r in results)
    assert results[0]['data'] == {'id': 'a'}
    assert results[1]['data'] == {'id': 'b'}


def test_multi_profile_isolation_mixed_exit_2(capsys):
    def dispatch(argv):
        if argv[-1] == 'b':
            raise AuthExpiredError('token expired')
        print('{"id":"' + argv[-1] + '"}')
        return 0

    rc = modes.run_with_output_modes('owa-mail', ['--profile', 'a', '--profile', 'b', 'messages'], dispatch)

    assert rc == 2
    payload = json.loads(capsys.readouterr().out)
    results = payload['results']
    assert results[0] == {'profile': 'a', 'ok': True, 'data': {'id': 'a'}}
    assert results[1]['profile'] == 'b'
    assert results[1]['ok'] is False
    assert results[1]['error'] == 'token expired'
    assert results[1]['exit_code'] == 11


def test_multi_profile_all_fail_exit_1(capsys):
    def dispatch(_argv):
        raise AuthExpiredError('token expired')

    rc = modes.run_with_output_modes('owa-mail', ['--profile', 'a', '--profile', 'b', 'messages'], dispatch)

    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    assert all(r['ok'] is False for r in payload['results'])


def test_multi_profile_pretty_sections(capsys):
    def dispatch(argv):
        print('row for ' + argv[-1])
        return 0

    rc = modes.run_with_output_modes(
        'owa-mail', ['--profile', 'a', '--profile', 'b', 'messages', '--pretty'], dispatch
    )

    assert rc == 0
    out = capsys.readouterr().out
    assert '=== profile: a ===' in out
    assert '=== profile: b ===' in out
    assert 'row for a' in out
    assert 'row for b' in out
    # Order preserved: a's section precedes b's.
    assert out.index('=== profile: a ===') < out.index('=== profile: b ===')


def test_multi_profile_ndjson_tags_each_line(capsys):
    def dispatch(argv):
        print('{"id":"' + argv[-1] + '-1"}')
        print('{"id":"' + argv[-1] + '-2"}')
        return 0

    rc = modes.run_with_output_modes(
        'owa-mail', ['--profile', 'a', '--profile', 'b', 'messages', '--ndjson'], dispatch
    )

    assert rc == 0
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert len(lines) == 4
    assert all('profile' in obj for obj in lines)
    assert [obj['profile'] for obj in lines] == ['a', 'a', 'b', 'b']
    assert lines[0]['item'] == {'id': 'a-1'}


def test_multi_profile_refuses_interactive(capsys):
    launched = []
    rc = modes.run_with_output_modes(
        'owa-mail',
        ['--profile', 'a', '--profile', 'b', 'tui'],
        lambda _argv: launched.append(True) or 0,
        interactive_commands=('tui',),
    )

    assert rc == 2
    assert launched == []
    assert 'cannot fan out' in capsys.readouterr().err


def test_multi_profile_refuses_binary(capsys):
    launched = []
    rc = modes.run_with_output_modes(
        'owa-drive',
        ['--profile', 'a', '--profile', 'b', 'get', '/Report.pdf'],
        lambda _argv: launched.append(True) or 0,
        binary_stdout_commands=('get',),
    )

    assert rc == 2
    assert launched == []
    assert 'cannot fan out' in capsys.readouterr().err


def test_fan_out_disabled_passes_full_argv_once():
    seen = []

    def dispatch(argv):
        seen.append(argv)
        return 0

    rc = modes.run_with_output_modes(
        'owa-mail',
        ['--profile', 'a', '--profile', 'b', 'messages'],
        dispatch,
        fan_out_profiles=False,
    )

    assert rc == 0
    # Repeated --profile is NOT fanned out; the full filtered argv is passed
    # once (the doctor opt-out path).
    assert seen == [['--profile', 'a', '--profile', 'b', 'messages']]
