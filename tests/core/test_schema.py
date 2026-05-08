"""Tests for shared schema helpers."""
import json

from owa_core import schema

COMMANDS = [
    schema.command('one', 'First command', auth='graph', flags=['--pretty']),
    schema.command('two', 'Second command', output='bytes'),
]


def test_command_builds_minimal_contract():
    row = COMMANDS[0]
    assert row['name'] == 'one'
    assert row['auth'] == {'audience': 'graph'}
    assert row['output'] == {'type': 'json'}
    assert row['flags'] == ['--pretty']


def test_schema_for_wraps_suite_metadata():
    payload = schema.schema_for('owa-test', COMMANDS)
    assert payload['tool'] == 'owa-test'
    assert payload['suite'] == 'owa-tools'
    assert payload['schema_version'] == 1
    assert payload['commands'] == COMMANDS


def test_emit_json_writes_pretty_json(capsys):
    assert schema.emit_json({'ok': True}) == 0
    assert json.loads(capsys.readouterr().out) == {'ok': True}


def test_maybe_emit_schema_ignores_regular_argv():
    assert schema.maybe_emit_schema(['events'], tool='owa-test', commands=COMMANDS) is None


def test_maybe_emit_schema_outputs_json_help(capsys):
    rc = schema.maybe_emit_schema(['--help', '--json'], tool='owa-test', commands=COMMANDS)
    assert rc == 0
    assert json.loads(capsys.readouterr().out)['tool'] == 'owa-test'


def test_maybe_emit_schema_filters_command(capsys):
    rc = schema.maybe_emit_schema(['schema', 'two'], tool='owa-test', commands=COMMANDS)
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert [command['name'] for command in payload['commands']] == ['two']


def test_maybe_emit_schema_rejects_unknown_command(capsys):
    rc = schema.maybe_emit_schema(['schema', 'missing'], tool='owa-test', commands=COMMANDS)
    assert rc == 2
    assert 'unknown schema command' in capsys.readouterr().err


def test_maybe_emit_schema_rejects_too_many_args(capsys):
    rc = schema.maybe_emit_schema(['schema', 'one', 'two'], tool='owa-test', commands=COMMANDS)
    assert rc == 2
    assert 'at most one command' in capsys.readouterr().err
