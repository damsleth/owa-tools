"""Argument parsing for `owa-places`."""

import json
import os
import sys

from owa_core import modes as mode_mod
from owa_core import schema as schema_mod
from owa_core.errors import UsageError, emit_message

from . import __version__
from . import api as api_mod
from . import auth as auth_mod
from . import config as config_mod
from . import places as places_mod
from .format import format_locations


def _debug_enabled(config):
    return bool(config.get('debug')) or os.environ.get('PLACES_DEBUG') == '1'


def _require_value(flag, args):
    if not args:
        raise UsageError(f'{flag} requires a value')
    return args[0], args[1:]


def _require_int(flag, args):
    value, args = _require_value(flag, args)
    try:
        return int(value), args
    except ValueError as exc:
        raise UsageError(f'{flag} requires an integer') from exc


def _info(message):
    emit_message(message, exit_code=0)


def print_help():
    print("""owa-places - Outlook meeting rooms and locations

Usage: owa-places <command> [options]

Commands:
  rooms       List room-like locations
  locations   List meeting locations
  recent      Alias for locations
  schema      Print machine-readable command schema

Options:
  --query <q>        Filter normalized name/email/building/floor
  --limit <n>        Maximum rows to return (default: 25)
  --cv <value>       SchedulingB2 correlation/version value
  --pretty           Human-readable table
  --profile <alias>  owa-piggy profile for this invocation
""")


def _fetch_locations(args, config, access_token, api_base, *, rooms_only):
    query = ''
    limit = 25
    pretty = False
    cv = api_mod.DEFAULT_CV
    while args:
        flag, args = args[0], args[1:]
        if flag == '--query':
            query, args = _require_value(flag, args)
        elif flag == '--limit':
            limit, args = _require_int(flag, args)
        elif flag == '--cv':
            cv, args = _require_value(flag, args)
        elif flag == '--pretty':
            pretty = True
        else:
            raise UsageError(f'Unknown flag: {flag}')
    if limit < 0:
        raise UsageError('--limit must be non-negative')
    payload = api_mod.scheduling_post(
        api_base,
        access_token,
        {'NumberOfLocations': limit or 25},
        cv=cv,
        debug=_debug_enabled(config),
    )
    rows = places_mod.filter_locations(
        places_mod.normalize_locations(payload or {}),
        query=query,
        rooms_only=rooms_only,
        limit=limit,
    )
    if pretty:
        print(format_locations(rows))
    else:
        print(json.dumps(rows, ensure_ascii=False))
    return 0


def cmd_locations(args, config, access_token, api_base):
    return _fetch_locations(args, config, access_token, api_base, rooms_only=False)


def cmd_rooms(args, config, access_token, api_base):
    return _fetch_locations(args, config, access_token, api_base, rooms_only=True)


AUTHED_COMMANDS = {'rooms', 'locations', 'recent'}

_LOCATION_FLAGS = [
    schema_mod.flag('--query', value='<text>', summary='Filter normalized locations'),
    schema_mod.flag('--limit', value='<n>', summary='Maximum rows to return'),
    schema_mod.flag('--cv', value='<value>', summary='SchedulingB2 correlation/version value'),
    schema_mod.flag('--pretty', summary='Human-readable table'),
]

COMMAND_SCHEMA = [
    schema_mod.command('rooms', 'List Outlook room-like meeting locations', auth='outlook', flags=_LOCATION_FLAGS),
    schema_mod.command('locations', 'List Outlook meeting locations', auth='outlook', flags=_LOCATION_FLAGS),
    schema_mod.command('recent', 'Alias for locations', auth='outlook', flags=_LOCATION_FLAGS),
]

COMMAND_SCOPES = {cmd: frozenset({'Calendars.Read', 'Calendars.ReadWrite'}) for cmd in AUTHED_COMMANDS}


def _main(argv):
    handled = schema_mod.maybe_emit_schema(argv, tool='owa-places', commands=COMMAND_SCHEMA)
    if handled is not None:
        return handled
    if not argv:
        print_help()
        return 0
    if argv[0] in ('help', '--help', '-h'):
        print_help()
        return 0
    if argv[0] in ('--version', '-v'):
        print(f'owa-places {__version__}')
        return 0

    # Strip global flags from anywhere in argv. A single --profile/-p pins the
    # owa-piggy profile for this run; repeated --profile / --all-profiles
    # fan-out is handled upstream in run_with_output_modes.
    profile_override = ''
    debug_flag = False
    filtered = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ('--debug', '--verbose'):
            debug_flag = True
        elif a in ('--profile', '-p'):
            if i + 1 >= len(argv):
                raise UsageError('--profile requires a value')
            profile_override = argv[i + 1]
            i += 2
            continue
        else:
            filtered.append(a)
        i += 1
    argv = filtered
    if not argv:
        print_help()
        return 0

    cmd, rest = argv[0], argv[1:]
    help_rc = schema_mod.maybe_emit_subcommand_help(cmd, rest, tool='owa-places', commands=COMMAND_SCHEMA)
    if help_rc is not None:
        return help_rc
    if cmd not in AUTHED_COMMANDS:
        raise UsageError(f'Unknown command: {cmd}')
    config = config_mod.load_config()
    if debug_flag:
        config['debug'] = True
    if profile_override:
        config['owa_piggy_profile'] = profile_override
    access_token, api_base = auth_mod.setup_auth(config, debug=_debug_enabled(config))
    if cmd == 'rooms':
        return cmd_rooms(rest, config, access_token, api_base)
    if cmd in {'locations', 'recent'}:
        return cmd_locations(rest, config, access_token, api_base)
    raise UsageError(f'Unknown command: {cmd}')


def main(argv=None):
    return mode_mod.run_with_output_modes(
        'owa-places',
        sys.argv[1:] if argv is None else argv,
        _main,
        audience=auth_mod.AUDIENCE,
        command_scopes=COMMAND_SCOPES,
    )
