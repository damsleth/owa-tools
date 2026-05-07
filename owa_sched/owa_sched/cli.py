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

from . import __version__
from . import api as api_mod
from . import auth as auth_mod
from . import config as config_mod
from .dates import (
    current_year,
    daterange,
    iso_week_range,
    make_local_iso,
    parse_hhmm,
    resolve_date,
    today,
)
from .format import format_availability_pretty, format_slots_pretty
from .schedule import find_open_slots, normalize_attendee


def _error(msg):
    print(f'ERROR: {msg}', file=sys.stderr)


def _info(msg):
    print(msg, file=sys.stderr)


def _debug_enabled(config):
    return bool(config.get('debug')) or os.environ.get('SCHED_DEBUG') == '1'


def _require_value(flag, args):
    if not args:
        _error(f'{flag} requires a value'); sys.exit(1)
    return args[0], args[1:]


def _require_int(flag, args):
    v, args = _require_value(flag, args)
    try:
        return int(v), args
    except ValueError:
        _error(f'{flag} requires an integer, got: {v}'); sys.exit(1)


def _split_csv(s):
    return [p.strip() for p in (s or '').split(',') if p.strip()]


def _resolve_window(date_, from_, to_, week, year):
    """Return (start_date, end_date) inclusive."""
    if week:
        year = year or current_year()
        from_, to_ = iso_week_range(week, year)
    elif date_:
        from_ = to_ = date_
    elif not from_:
        from_ = to_ = today()
    if not to_:
        to_ = from_
    return from_, to_


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
  --date <date>       Single day (YYYY-MM-DD, today, tomorrow, yesterday).
  --from <date>       Start of range.
  --to <date>         End of range.
  --week <n>          ISO week number.
  --year <n>          Year (default: current).
  --start <HH:MM>     Window start time (default: 08:00).
  --end <HH:MM>       Window end time (default: 17:00).
  --interval <n>      availabilityView granularity in minutes (default: 30).
  --pretty            Human-readable output (default: JSON).

find-time options:
  --who <emails>      Comma-separated attendees (required, includes self
                      if you want to be checked too).
  --duration <n>      Slot length in minutes (default: 30).
  --date / --from / --to / --week / --year  - same as availability.
  --start <HH:MM>     Earliest start of working day (default: 09:00).
  --end <HH:MM>       Latest end of working day (default: 17:00).
  --pretty            Human-readable output (default: JSON list of slots).

Examples:
  owa-sched availability --who alice@x.com,bob@x.com --week 19 --pretty
  owa-sched availability --who vibeke@une.no --date tomorrow --pretty
  owa-sched find-time --who alice@x.com,bob@x.com --duration 30 --week 19 --pretty
  owa-sched --profile crayon find-time --who ole@example.com --date 2026-05-12
""")


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
    week = year = 0
    start_hhmm = '08:00'
    end_hhmm = '17:00'
    interval = 30
    pretty = False
    while args:
        flag, args = args[0], args[1:]
        if flag == '--who':
            who_csv, args = _require_value(flag, args)
        elif flag == '--date':
            v, args = _require_value(flag, args); date_ = resolve_date(v)
        elif flag == '--from':
            v, args = _require_value(flag, args); from_ = resolve_date(v)
        elif flag == '--to':
            v, args = _require_value(flag, args); to_ = resolve_date(v)
        elif flag == '--week':
            week, args = _require_int(flag, args)
        elif flag == '--year':
            year, args = _require_int(flag, args)
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
            _error(f'Unknown flag: {flag}'); sys.exit(1)

    who = _split_csv(who_csv)
    if not who:
        _error('--who is required (comma-separated emails)')
        return 1

    from_, to_ = _resolve_window(date_, from_, to_, week, year)
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
    week = year = 0
    duration = 30
    start_hhmm = config.get('default_work_start') or '09:00'
    end_hhmm = config.get('default_work_end') or '17:00'
    pretty = False
    while args:
        flag, args = args[0], args[1:]
        if flag == '--who':
            who_csv, args = _require_value(flag, args)
        elif flag == '--duration':
            duration, args = _require_int(flag, args)
        elif flag == '--date':
            v, args = _require_value(flag, args); date_ = resolve_date(v)
        elif flag == '--from':
            v, args = _require_value(flag, args); from_ = resolve_date(v)
        elif flag == '--to':
            v, args = _require_value(flag, args); to_ = resolve_date(v)
        elif flag == '--week':
            week, args = _require_int(flag, args)
        elif flag == '--year':
            year, args = _require_int(flag, args)
        elif flag == '--start':
            start_hhmm, args = _require_value(flag, args)
            parse_hhmm(start_hhmm)
        elif flag == '--end':
            end_hhmm, args = _require_value(flag, args)
            parse_hhmm(end_hhmm)
        elif flag == '--pretty':
            pretty = True
        else:
            _error(f'Unknown flag: {flag}'); sys.exit(1)

    who = _split_csv(who_csv)
    if not who:
        _error('--who is required (comma-separated emails)')
        return 1
    if duration <= 0:
        _error('--duration must be positive')
        return 1

    from_, to_ = _resolve_window(date_, from_, to_, week, year)
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
            _error(f'Unknown flag: {flag}'); sys.exit(1)

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
        _error(f'Unknown flag: {args[0]}'); sys.exit(1)
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


def main():
    argv = sys.argv[1:]
    if not argv:
        print_help()
        return 0
    if argv[0] in ('help', '--help', '-h'):
        print_help()
        return 0
    if argv[0] == '--version':
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
                _error('--profile requires a value'); return 1
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
        _error(f"Unknown command: {cmd}. Run 'owa-sched help' for usage.")
        return 1

    access_token, api_base = auth_mod.setup_auth(
        config, debug=_debug_enabled(config),
    )

    if cmd == 'availability':
        return cmd_availability(rest, config, access_token, api_base)
    if cmd == 'find-time':
        return cmd_find_time(rest, config, access_token, api_base)

    return 1
