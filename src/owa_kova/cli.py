"""Argument parsing for `owa-kova`."""

import datetime
import json
import os
import sys

from owa_core import modes as mode_mod
from owa_core import schema as schema_mod
from owa_core.errors import UsageError, _require_value

from . import __version__
from . import schedule as schedule_mod
from . import session as session_mod

DUTIES = '/api/default/GetOpenDuties?pStartDate={start}&pOnlyMine={mine}'


def _debug_enabled(config):
    return bool(config.get('debug')) or os.environ.get('KOVA_DEBUG') == '1'


def print_help():
    print("""owa-kova - read-only Kova (Red Cross) schedule

Usage: owa-kova <command> [options]

Commands:
  schedule      Your duties (shifts) from today, about two months ahead
  schema        Print machine-readable command schema

Options:
  --from <YYYY-MM-DD>  Start date (default: today); Kova returns ~2 months
  --open               Every duty in the unit, not just yours
  --pretty             Human-readable output
  --profile <alias>    owa-piggy profile with Kova (default: the default or only one)
""")
    print(schema_mod.MULTI_PROFILE_HELP)
    print()
    print(schema_mod.MACHINE_SURFACE_HELP)


def _parse(args):
    opts = {}
    while args:
        flag, args = args[0], args[1:]
        if flag in ('--pretty', '--open'):
            opts[flag] = True
        elif flag == '--from':
            value, args = _require_value(flag, args)
            try:
                datetime.date.fromisoformat(value)
            except ValueError as exc:
                raise UsageError(f'--from needs YYYY-MM-DD, got {value!r}') from exc
            opts[flag] = value
        else:
            raise UsageError(f'Unknown flag: {flag}' if flag.startswith('-') else f'Unexpected argument: {flag}')
    return opts


def _format(rows):
    lines = []
    for r in rows:
        when = r['when'] if not r['start'] else f"{r['start'].replace('T', ' ')} - {(r['end'] or '')[-5:]}"
        flags = ' '.join(f for f, on in (('[mine]', r['mine']), ('[full]', r['full']), ('[locked]', r['locked'])) if on)
        role = f" ({r['my_role']})" if r['my_role'] else ''
        lines.append(f"{when}  {r['event']} - {r['duty']}{role} {flags}".rstrip())
    return '\n'.join(lines) or 'no duties'


def cmd_schedule(args, config):
    opts = _parse(args)
    path = DUTIES.format(start=opts.get('--from', ''), mine='false' if opts.get('--open') else 'true')
    log = (lambda m: print(f'DEBUG: {m}', file=sys.stderr)) if _debug_enabled(config) else None
    [fragment] = session_mod.fetch_json([path], profile=config.get('owa_piggy_profile'), log=log)
    rows = schedule_mod.parse_duties(fragment if isinstance(fragment, str) else '')
    if opts.get('--pretty'):
        print(_format(rows))
    else:
        print(json.dumps(rows, ensure_ascii=False))
    return 0


COMMANDS = {'schedule': cmd_schedule}

COMMAND_SCHEMA = [
    schema_mod.command('schedule', 'Your Kova duties (or every open duty with --open)', flags=[
        schema_mod.flag('--from', value='<YYYY-MM-DD>', summary='Start date; Kova returns about two months'),
        schema_mod.flag('--open', summary="Every duty in the unit, not just yours"),
        schema_mod.flag('--pretty', summary='Human-readable output'),
    ]),
]


def _main(argv):
    handled = schema_mod.maybe_emit_schema(argv, tool='owa-kova', commands=COMMAND_SCHEMA)
    if handled is not None:
        return handled
    if not argv or argv[0] in ('help', '--help', '-h'):
        print_help()
        return 0
    if argv[0] in ('--version', '-v'):
        print(f'owa-kova {__version__}')
        return 0
    config = {}
    filtered = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ('--debug', '--verbose'):
            config['debug'] = True
        elif a in ('--profile', '-p'):
            if i + 1 >= len(argv):
                raise UsageError('--profile requires a value')
            config['owa_piggy_profile'] = argv[i + 1]
            i += 1
        else:
            filtered.append(a)
        i += 1
    if not filtered:
        print_help()
        return 0
    cmd, rest = filtered[0], filtered[1:]
    help_rc = schema_mod.maybe_emit_subcommand_help(cmd, rest, tool='owa-kova', commands=COMMAND_SCHEMA)
    if help_rc is not None:
        return help_rc
    if cmd not in COMMANDS:
        raise UsageError(f'Unknown command: {cmd}')
    return COMMANDS[cmd](rest, config)


def main(argv=None):
    return mode_mod.run_with_output_modes(
        'owa-kova',
        sys.argv[1:] if argv is None else argv,
        _main,
        commands=COMMAND_SCHEMA,
        service=session_mod.SERVICE,
    )
