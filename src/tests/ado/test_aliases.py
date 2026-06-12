"""Command aliases resolve to their canonical owa-ado verbs."""
from owa_ado import cli as cli_mod
from owa_core import schema as schema_mod


def test_aliases_resolve():
    cmds = cli_mod.COMMAND_SCHEMA
    assert schema_mod.resolve_alias('workitems', cmds) == 'wi'
    assert schema_mod.resolve_alias('iterations', cmds) == 'sprints'
    assert schema_mod.resolve_alias('repositories', cmds) == 'repos'
    # Canonical names pass through unchanged.
    assert schema_mod.resolve_alias('projects', cmds) == 'projects'


def test_every_authed_command_has_schema_entry():
    schema_names = {c['name'] for c in cli_mod.COMMAND_SCHEMA}
    assert cli_mod.AUTHED_COMMANDS <= schema_names
