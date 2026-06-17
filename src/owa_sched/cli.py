"""Argument parsing and dispatch for `owa-sched`.

Two main subcommands:
  availability   - per-attendee busy listing
  find-time      - naive multi-attendee slot finder

Both call POST /me/calendar/getSchedule. The slot finder layers
pure-function logic in `schedule.find_open_slots` on top of the
same response.
"""
import json
import os
import sys

from owa_core import modes as mode_mod
from owa_core import periods as periods_mod
from owa_core import schema as schema_mod
from owa_core.errors import UsageError, emit_message

from . import __version__
from . import api as api_mod
from . import auth as auth_mod
from . import config as config_mod
from .dates import (
    daterange,
    iso_week_range,
    make_local_iso,
    parse_hhmm,
)
from .format import format_availability_pretty, format_slots_pretty
from .schedule import find_open_slots, normalize_attendee


def _error(msg):
    emit_message(msg)


def _info(msg):
    print(msg, file=sys.stderr)


def _debug_enabled(config):
    return bool(config.get('debug')) or os.environ.get('SCHED_DEBUG') == '1'


def _require_value(flag, args):
    if not args:
        raise UsageError(f'{flag} requires a value')
    return args[0], args[1:]


def _require_int(flag, args):
    v, args = _require_value(flag, args)
    try:
        return int(v), args
    except ValueError:
        raise UsageError(f'{flag} requires an integer, got: {v}')


def _optional_value(args, default):
    """Consume the next token as a value unless it is missing or is another
    flag (`--xxx`), so bare `--month` means the current month while
    `--month next` / `--month -1` still work (every owa-sched flag is
    double-dashed, so signed offsets read as values)."""
    if args and not args[0].startswith('--'):
        return args[0], args[1:]
    return default, args


def _split_csv(s):
    return [p.strip() for p in (s or '').split(',') if p.strip()]


def _resolve_window(date_, from_, to_, week, month, year):
    """Return (start_date, end_date) inclusive.

    Delegates to the shared owa_core.periods resolver with owa-sched's
    Mon-Fri work-week shape. Accepts the full relative/semantic vocabulary
    (current/last/next/+n/-n) and raises UsageError on conflicting flags.
    """
    return periods_mod.resolve_window(
        iso_week_range=iso_week_range,
        date_=date_, from_=from_, to_=to_,
        week=week, month=month, year=year,
    )


def print_help():
    print("""owa-sched - Scheduling assistant for Outlook / Microsoft 365

Usage: owa-sched <command> [options]

Global options:
  --debug, --verbose  Print HTTP requests and response bodies on errors
                      (also: SCHED_DEBUG=1)
  --profile <alias>   Forward to owa-piggy as --profile <alias>.

Commands:
  availability        Per-attendee free/busy listing in a window.
  find-time           Find open slots when every attendee is free.
  refresh             Force a token refresh and verify auth.
  config              View or update configuration.
  help                Show this help.

availability options:
  --who <emails>      Comma-separated list of attendee emails (required).
  --date <date>       Single day. YYYY-MM-DD, today/tomorrow/yesterday, a
                      signed day offset (+1, -3), or a weekday name in the
                      current ISO week with optional week offset
                      (monday, monday+1, friday-2).
  --from <date>       Start of range (same vocabulary as --date).
  --to <date>         End of range (same vocabulary as --date).
  --week <n|rel>      ISO work week (Mon-Fri): number, current/last/next, +n/-n.
  --month <n|rel>     Calendar month: 1-12, current/last/next, +n/-n
                      (bare --month = current).
  --year <n|rel>      Year: full year, current/last/next, +n/-n. Combine with
                      --week/--month, or use alone for the whole year.
  --start <HH:MM>     Work-day window start (default: 08:00, or config
                      default_work_start).
  --end <HH:MM>       Work-day window end (default: 17:00, or config
                      default_work_end).
  --interval <n>      availabilityView granularity in minutes (default: 30).
  --pretty            Human-readable output (default: JSON).

find-time options:
  --who <emails>      Comma-separated attendees (required, includes self
                      if you want to be checked too).
  --duration <n>      Slot length in minutes (default: 30).
  --date / --from / --to / --week / --month / --year  - same as availability.
  --start <HH:MM>     Work-day window start (default: 08:00, or config
                      default_work_start).
  --end <HH:MM>       Work-day window end (default: 17:00, or config
                      default_work_end).
  --pretty            Human-readable output (default: JSON list of slots).

Examples:
  owa-sched availability --who alice@x.com,bob@x.com --week 19 --pretty
  owa-sched availability --who alice@x.com,bob@x.com --week next --pretty
  owa-sched availability --who alice@x.com --month --pretty
  owa-sched availability --who vibeke@une.no --date tomorrow --pretty
  owa-sched find-time --who alice@x.com,bob@x.com --duration 30 --week 19 --pretty
  owa-sched --profile crayon find-time --who ole@example.com --date 2026-05-12
""")
    print()
    print(schema_mod.MULTI_PROFILE_HELP)
    print()
    print(schema_mod.MACHINE_SURFACE_HELP)


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

def _call_get_schedule(who, from_date, to_date, start_hhmm, end_hhmm,
                       interval, tz, access_token, api_base, debug):
    """Issue one POST /me/calendar/getSchedule call covering the
    full window. The endpoint accepts a single (start, end) pair, so
    we don't paginate per-day - we span the whole window."""
    body = {
        'schedules': who,
        'startTime': {
            'dateTime': make_local_iso(from_date, start_hhmm),
            'timeZone': tz,
        },
        'endTime': {
            'dateTime': make_local_iso(to_date, end_hhmm),
            'timeZone': tz,
        },
        'availabilityViewInterval': interval,
    }
    payload = api_mod.api_post(
        api_base, 'me/calendar/getSchedule', access_token,
        body=body, debug=debug,
    )
    if payload is None:
        return None
    items = payload.get('value') or []
    return [normalize_attendee(it) for it in items]


def cmd_availability(args, config, access_token, api_base):
    who_csv = ''
    date_ = from_ = to_ = ''
    week = month = year = ''
    start_hhmm = config.get('default_work_start') or '08:00'
    end_hhmm = config.get('default_work_end') or '17:00'
    interval = 30
    pretty = False
    while args:
        flag, args = args[0], args[1:]
        if flag == '--who':
            who_csv, args = _require_value(flag, args)
        elif flag == '--date':
            date_, args = _require_value(flag, args)
        elif flag == '--from':
            from_, args = _require_value(flag, args)
        elif flag == '--to':
            to_, args = _require_value(flag, args)
        elif flag == '--week':
            week, args = _require_value(flag, args)
        elif flag == '--month':
            month, args = _optional_value(args, 'current')
        elif flag == '--year':
            year, args = _require_value(flag, args)
        elif flag == '--start':
            start_hhmm, args = _require_value(flag, args)
            parse_hhmm(start_hhmm)
        elif flag == '--end':
            end_hhmm, args = _require_value(flag, args)
            parse_hhmm(end_hhmm)
        elif flag == '--interval':
            interval, args = _require_int(flag, args)
        elif flag == '--pretty':
            pretty = True
        else:
            raise UsageError(f'Unknown flag: {flag}')

    who = _split_csv(who_csv)
    if not who:
        raise UsageError('--who is required (comma-separated emails)')

    from_, to_ = _resolve_window(date_, from_, to_, week, month, year)
    tz = config.get('default_timezone') or 'W. Europe Standard Time'

    attendees = _call_get_schedule(
        who, from_, to_, start_hhmm, end_hhmm, interval, tz,
        access_token, api_base, debug=_debug_enabled(config),
    )
    if attendees is None:
        return 1

    if pretty:
        print(format_availability_pretty(attendees))
    else:
        print(json.dumps(attendees))
    return 0


def cmd_find_time(args, config, access_token, api_base):
    who_csv = ''
    date_ = from_ = to_ = ''
    week = month = year = ''
    duration = 30
    start_hhmm = config.get('default_work_start') or '08:00'
    end_hhmm = config.get('default_work_end') or '17:00'
    pretty = False
    while args:
        flag, args = args[0], args[1:]
        if flag == '--who':
            who_csv, args = _require_value(flag, args)
        elif flag == '--duration':
            duration, args = _require_int(flag, args)
        elif flag == '--date':
            date_, args = _require_value(flag, args)
        elif flag == '--from':
            from_, args = _require_value(flag, args)
        elif flag == '--to':
            to_, args = _require_value(flag, args)
        elif flag == '--week':
            week, args = _require_value(flag, args)
        elif flag == '--month':
            month, args = _optional_value(args, 'current')
        elif flag == '--year':
            year, args = _require_value(flag, args)
        elif flag == '--start':
            start_hhmm, args = _require_value(flag, args)
            parse_hhmm(start_hhmm)
        elif flag == '--end':
            end_hhmm, args = _require_value(flag, args)
            parse_hhmm(end_hhmm)
        elif flag == '--pretty':
            pretty = True
        else:
            raise UsageError(f'Unknown flag: {flag}')

    who = _split_csv(who_csv)
    if not who:
        raise UsageError('--who is required (comma-separated emails)')
    if duration <= 0:
        raise UsageError('--duration must be positive')

    from_, to_ = _resolve_window(date_, from_, to_, week, month, year)
    tz = config.get('default_timezone') or 'W. Europe Standard Time'

    # Use a fine-grained interval (15 min) so the slot finder can place
    # candidates on quarter-hour boundaries even for 30-min meetings.
    interval = 15

    attendees = _call_get_schedule(
        who, from_, to_, start_hhmm, end_hhmm, interval, tz,
        access_token, api_base, debug=_debug_enabled(config),
    )
    if attendees is None:
        return 1

    # Build candidate windows: one per day, bounded by the work-day
    # start/end. Open slots are computed per-day to keep the work-day
    # boundary honest (no overnight slots).
    all_slots = []
    for d in daterange(from_, to_):
        day_start = make_local_iso(d, start_hhmm)
        day_end = make_local_iso(d, end_hhmm)
        all_slots.extend(
            find_open_slots(attendees, day_start, day_end, duration)
        )

    if pretty:
        print(format_slots_pretty(all_slots))
    else:
        print(json.dumps([
            {'start': s, 'end': e} for s, e in all_slots
        ]))
    return 0


def cmd_config(args, config):
    profile = ''
    while args:
        flag, args = args[0], args[1:]
        if flag == '--profile':
            profile, args = _require_value(flag, args)
        else:
            raise UsageError(f'Unknown flag: {flag}')

    if profile:
        config_mod.config_set('owa_piggy_profile', profile)
        _info(f'default profile saved: {profile}')
        return 0

    _info(f'Config file: {config_mod.CONFIG_PATH}')
    if config.get('owa_piggy_profile'):
        _info(f"  owa_piggy_profile={config.get('owa_piggy_profile')}")
    else:
        _info('  owa_piggy_profile=(not set - owa-piggy picks its default)')
    _info(f"  default_timezone={config.get('default_timezone')}")
    _info(f"  default_work_start={config.get('default_work_start')}")
    _info(f"  default_work_end={config.get('default_work_end')}")
    return 0


def cmd_refresh(args, config):
    if args:
        raise UsageError(f'Unknown flag: {args[0]}')
    _info('Refreshing token...')
    access = auth_mod.do_token_refresh(config, debug=_debug_enabled(config))
    if not access:
        _error('Token refresh failed.')
        return 1
    me = api_mod.api_request(
        'GET', 'https://graph.microsoft.com/v1.0', 'me', access,
        debug=_debug_enabled(config),
    )
    if not isinstance(me, dict):
        _error('Auth verification failed.')
        return 1
    name = me.get('displayName')
    if name:
        _info(f'Authenticated as {name}')
    return 0


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

AUTHED_COMMANDS = {'availability', 'find-time'}


def _command_name(argv):
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ('--debug', '--verbose'):
            i += 1
            continue
        if a == '--profile':
            i += 2
            continue
        return a
    return ''


_AVAILABILITY_FLAGS = [
    schema_mod.flag('--who', value='<addr[,addr]>', summary='Comma-separated attendee emails', required=True),
    schema_mod.flag('--date', value='<date>', summary='Specific day (YYYY-MM-DD, today/tomorrow/yesterday, +n/-n, weekday[+n])'),
    schema_mod.flag('--from', value='<date>', summary='Start of range'),
    schema_mod.flag('--to', value='<date>', summary='End of range'),
    schema_mod.flag('--week', value='<n|rel>', summary='ISO work week: number, current/last/next, or +n/-n'),
    schema_mod.flag('--month', value='<n|rel>', summary='Month: 1-12, current/last/next, or +n/-n (bare = current)'),
    schema_mod.flag('--year', value='<n|rel>', summary='Year: full year, current/last/next, or +n/-n'),
    schema_mod.flag('--start', value='<HH:MM>', summary='Work-day start (default 08:00, or config default_work_start)'),
    schema_mod.flag('--end', value='<HH:MM>', summary='Work-day end (default 17:00, or config default_work_end)'),
    schema_mod.flag('--interval', value='<min>', summary='Resolution in minutes (default 30)'),
    schema_mod.flag('--pretty', summary='Human-readable view (default: JSON)'),
]

_FIND_TIME_FLAGS = [
    schema_mod.flag('--who', value='<addr[,addr]>', summary='Comma-separated attendee emails', required=True),
    schema_mod.flag('--duration', value='<min>', summary='Meeting length in minutes (default 30)'),
    schema_mod.flag('--date', value='<date>', summary='Specific day (YYYY-MM-DD, today/tomorrow/yesterday, +n/-n, weekday[+n])'),
    schema_mod.flag('--from', value='<date>', summary='Start of range'),
    schema_mod.flag('--to', value='<date>', summary='End of range'),
    schema_mod.flag('--week', value='<n|rel>', summary='ISO work week: number, current/last/next, or +n/-n'),
    schema_mod.flag('--month', value='<n|rel>', summary='Month: 1-12, current/last/next, or +n/-n (bare = current)'),
    schema_mod.flag('--year', value='<n|rel>', summary='Year: full year, current/last/next, or +n/-n'),
    schema_mod.flag('--start', value='<HH:MM>', summary='Work-day start (default 08:00, or config default_work_start)'),
    schema_mod.flag('--end', value='<HH:MM>', summary='Work-day end (default 17:00, or config default_work_end)'),
    schema_mod.flag('--pretty', summary='Human-readable view (default: JSON)'),
]

_CONFIG_FLAGS = [
    schema_mod.flag('--profile', value='<alias>', summary='Pin a default owa-piggy profile alias (owa_piggy_profile)'),
]

COMMAND_SCHEMA = [
    schema_mod.command('availability', 'List attendee free/busy windows', auth='graph', flags=_AVAILABILITY_FLAGS),
    schema_mod.command('find-time', 'Find meeting slots', auth='graph', flags=_FIND_TIME_FLAGS),
    schema_mod.command('refresh', 'Force a token refresh', auth='graph'),
    schema_mod.command('config', 'View or update configuration', mutates=True, flags=_CONFIG_FLAGS),
]


def _main(argv):
    handled = schema_mod.maybe_emit_schema(argv, tool='owa-sched', commands=COMMAND_SCHEMA)
    if handled is not None:
        return handled

    if not argv:
        print_help()
        return 0
    if argv[0] in ('help', '--help', '-h'):
        print_help()
        return 0
    if argv[0] in ('--version', '-v'):
        print(f'owa-sched {__version__}')
        return 0

    debug_flag = False
    profile_override = ''
    is_config_cmd = _command_name(argv) == 'config'
    filtered = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ('--debug', '--verbose'):
            debug_flag = True
        elif a == '--profile' and not (is_config_cmd and 'config' in filtered):
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

    help_rc = schema_mod.maybe_emit_subcommand_help(
        cmd, rest, tool='owa-sched', commands=COMMAND_SCHEMA,
    )
    if help_rc is not None:
        return help_rc

    config = config_mod.load_config()
    if debug_flag:
        config['debug'] = True
        _info('DEBUG: verbose logging enabled')
    if profile_override:
        config['owa_piggy_profile'] = profile_override

    if cmd == 'config':
        return cmd_config(rest, config)
    if cmd == 'refresh':
        return cmd_refresh(rest, config)

    if cmd not in AUTHED_COMMANDS:
        raise UsageError(f"Unknown command: {cmd}. Run 'owa-sched help' for usage.")

    schema_mod.precheck_required_args(cmd, rest, commands=COMMAND_SCHEMA)

    access_token, api_base = auth_mod.setup_auth(
        config, debug=_debug_enabled(config),
    )

    if cmd == 'availability':
        return cmd_availability(rest, config, access_token, api_base)
    if cmd == 'find-time':
        return cmd_find_time(rest, config, access_token, api_base)

    return 1


# Delegated scopes that grant each scheduling command (any-of), used by the
# --profile all fan-out to silently skip profiles with no calendar access
# (getSchedule free/busy needs Calendars.Read). refresh/config are local.
_SCHED_SCOPES = frozenset({
    'Calendars.Read', 'Calendars.ReadWrite', 'Calendars.Read.Shared',
})
COMMAND_SCOPES = {cmd: _SCHED_SCOPES for cmd in ('availability', 'find-time')}


def main(argv=None):
    return mode_mod.run_with_output_modes(
        'owa-sched', sys.argv[1:] if argv is None else argv, _main,
        audience=auth_mod.AUDIENCE,
        command_scopes=COMMAND_SCOPES,
    )
