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


def test_command_can_declare_mutation_metadata():
    row = schema.command(
        'delete',
        'Delete item',
        mutates=True,
        destructive=True,
        confirmation=True,
        idempotent=False,
    )

    assert row['mutates'] is True
    assert row['destructive'] is True
    assert row['confirmation'] == {'flag': '--confirm'}
    assert row['idempotent'] is False


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


def test_flag_builds_minimal_spec():
    spec = schema.flag('--pretty')
    assert spec == {'name': '--pretty'}


def test_flag_records_value_and_required():
    spec = schema.flag(
        '--id', value='<event-id>', summary='Event ID', required=True,
    )
    assert spec == {
        'name': '--id',
        'value': '<event-id>',
        'summary': 'Event ID',
        'required': True,
    }


def test_flag_marks_repeatable():
    spec = schema.flag('--header', value='K=V', repeatable=True)
    assert spec['repeatable'] is True


def test_render_command_help_with_flag_dicts(capsys):
    cmd = schema.command(
        'create',
        'Create an event',
        flags=[
            schema.flag('--subject', value='<title>', summary='Event title', required=True),
            schema.flag('--pretty', summary='Human-readable'),
        ],
    )

    rc = schema.render_command_help('owa-cal', cmd)
    out = capsys.readouterr().out

    assert rc == 0
    assert 'Usage: owa-cal create [options]' in out
    assert 'Create an event' in out
    assert '--subject <title>' in out
    assert '(required)' in out
    assert '--pretty' in out


def test_render_command_help_with_bare_string_flags(capsys):
    cmd = schema.command('events', 'List events', flags=['--pretty', '--limit'])
    schema.render_command_help('owa-cal', cmd)
    out = capsys.readouterr().out
    assert '--pretty' in out
    assert '--limit' in out


def test_render_command_help_shows_destructive_notes(capsys):
    cmd = schema.command(
        'delete', 'Delete an event', auth='outlook',
        mutates=True, destructive=True, confirmation=True, idempotent=False,
    )
    schema.render_command_help('owa-cal', cmd)
    out = capsys.readouterr().out
    assert 'destructive' in out
    assert '--confirm' in out
    assert 'not idempotent' in out
    assert 'auth audience: outlook' in out


def test_render_command_help_handles_zero_flags(capsys):
    cmd = schema.command('refresh', 'Force a token refresh')
    schema.render_command_help('owa-cal', cmd)
    out = capsys.readouterr().out
    assert '(no flags)' in out


def test_maybe_emit_subcommand_help_returns_none_when_not_help():
    cmd = schema.command('events', 'List events')
    assert schema.maybe_emit_subcommand_help(
        'events', ['--pretty'], tool='owa-cal', commands=[cmd],
    ) is None


def test_maybe_emit_subcommand_help_does_not_steal_values_named_help():
    cmd = schema.command('find', 'Search people')
    assert schema.maybe_emit_subcommand_help(
        'find', ['help'], tool='owa-people', commands=[cmd],
    ) is None


def test_maybe_emit_subcommand_help_ignores_help_token_with_other_args():
    cmd = schema.command('send', 'Send mail')
    assert schema.maybe_emit_subcommand_help(
        'send', ['--body', '--help'], tool='owa-mail', commands=[cmd],
    ) is None


def test_maybe_emit_subcommand_help_returns_none_for_unknown_command():
    cmd = schema.command('events', 'List events')
    assert schema.maybe_emit_subcommand_help(
        'bogus', ['--help'], tool='owa-cal', commands=[cmd],
    ) is None


def test_maybe_emit_subcommand_help_short_form(capsys):
    cmd = schema.command('events', 'List events', flags=['--pretty'])
    rc = schema.maybe_emit_subcommand_help(
        'events', ['-h'], tool='owa-cal', commands=[cmd],
    )
    assert rc == 0
    assert 'Usage: owa-cal events' in capsys.readouterr().out


def test_maybe_emit_subcommand_help_long_form(capsys):
    cmd = schema.command('events', 'List events', flags=['--pretty'])
    rc = schema.maybe_emit_subcommand_help(
        'events', ['--help'], tool='owa-cal', commands=[cmd],
    )
    assert rc == 0
    assert 'Usage: owa-cal events' in capsys.readouterr().out


def test_is_help_token_only_matches_help_forms():
    assert schema.is_help_token('--help')
    assert schema.is_help_token('-h')
    assert not schema.is_help_token('help')
    assert not schema.is_help_token('--pretty')
    assert not schema.is_help_token('events')
