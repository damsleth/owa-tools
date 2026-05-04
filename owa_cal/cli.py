"""Argument parsing and dispatch for the `owa-cal` command.

owa-cal is pipe-friendly: JSON on stdout, logs on stderr. --pretty
switches stdout to a human-readable table. Exit codes follow POSIX
convention (0 success, 1 error).

Subcommands are parsed manually (no argparse subparsers) to keep the
code flat and to match the old zsh dispatch exactly. Each cmd_* fn is
responsible for its own flag loop.
"""
import json
import os
import sys
import urllib.parse
from datetime import datetime, timedelta

from . import api as api_mod
from . import auth as auth_mod
from . import config as config_mod
from . import events as events_mod
from .dates import (
    current_iso_week,
    iso_week_range,
    make_datetime,
    resolve_date,
    today,
)
from .format import format_events_pretty

# OData $select / $orderby fragments shared by `events` listing and the
# post-create duplicate check. Keep these in sync: the dupe check
# compares the same normalized fields the listing surfaces.
_EVENTS_SELECT = (
    'Id,Subject,Start,End,Location,Categories,ShowAs,IsAllDay,'
    'OriginalStartTimeZone,OriginalEndTimeZone'
)
_EVENTS_ORDERBY = 'Start/DateTime'


def _error(msg):
    print(f'ERROR: {msg}', file=sys.stderr)


def _info(msg):
    print(msg, file=sys.stderr)


def _debug_enabled(config):
    return bool(config.get('debug')) or os.environ.get('CAL_DEBUG') == '1'


def _event_path(event_id):
    return f'me/events/{urllib.parse.quote(event_id, safe="")}'


def _split_datetime(value):
    if not value or 'T' not in value:
        return '', ''
    return value.split('T', 1)


def _add_days(date_value, days):
    dt = datetime.strptime(date_value, '%Y-%m-%d')
    return (dt + timedelta(days=days)).strftime('%Y-%m-%d')


def _date_delta_days(start_date, end_date):
    if not start_date or not end_date:
        return 0
    start = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d')
    return (end - start).days


def _command_name(argv):
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ('--debug', '--verbose'):
            i += 1
            continue
        if arg == '--profile':
            i += 2
            continue
        return arg
    return ''


def print_help():
    """owa-cal help output. Kept verbatim to the zsh version so muscle
    memory still works."""
    print("""owa-cal - Calendar CLI for Outlook / Microsoft 365

Usage: owa-cal <command> [options]

Global options:
  --debug, --verbose  Print HTTP requests and response bodies on errors
                      (also: CAL_DEBUG=1)
  --profile <alias>   Forward to owa-piggy as --profile <alias> for
                      this invocation (overrides owa_piggy_profile in
                      the config file, and OWA_PROFILE in the env)

Environment:
  CAL_DEBUG=1         Same as --debug
  OWA_PROFILE=<alias> Inherited by the owa-piggy subprocess. Lower
                      precedence than --profile and the config file
                      pin, but useful for one-shot sessions
                      (`OWA_PROFILE=work owa-cal events`)
  OWA_REFRESH_TOKEN,  Env-only mode: passed through to owa-piggy so it
  OWA_TENANT_ID       can mint tokens with no on-disk config. Enables
                      `uvx owa-cal events` against a fresh machine
                      (see README -> Single-line uvx)

Commands:
  refresh             Force a token refresh and verify auth
  events              List calendar events (default: today)
  create              Create a new event
  update              Update an existing event
  delete              Delete an event
  categories          List or add master categories
  config              View or update configuration
  help                Show this help

Events options:
  --date <date>       Specific day (YYYY-MM-DD, today, tomorrow, yesterday)
  --from <date>       Start of range
  --to <date>         End of range
  --week <n>          ISO week number
  --year <n>          Year (default: current)
  --search <term>     Search events by subject
  --pretty            Human-readable table (default: JSON)
  --limit <n>         Max results (default: 50)

Create options:
  --subject <title>   Event title (required)
  --date <date>       Date (default: today)
  --start <HH:MM>     Start time (default: 09:00)
  --end <HH:MM>       End time (default: 10:00)
  --category <name>   Category name
  --location <place>  Location
  --body <text>       Description
  --allday            All-day event
  --showas <status>   busy, free, tentative, oof

Update options:
  --id <event-id>     Event ID (required)
  --subject, --date, --start, --end, --category,
  --location, --body, --showas

Delete options:
  --id <event-id>     Event ID (required)
  --confirm           Skip confirmation prompt

Categories options:
  --add <name>        Add a new master category
  --pretty            Human-readable table (default: JSON)
  (no flags)          List all categories as JSON

Config options:
  --profile <alias>   Pin an owa-piggy profile alias (owa_piggy_profile)

Auth:
  owa-cal shells out to owa-piggy for a fresh access token on every
  call. owa-piggy owns the token lifecycle; owa-cal stores nothing
  more than an optional profile alias.

  Quickstart:
    brew install damsleth/tap/owa-piggy
    owa-piggy setup                           # or: setup --profile work

Examples:
  owa-cal events --pretty
  owa-cal events --week 16 --pretty
  owa-cal events --from 2026-04-14 --to 2026-04-18 --pretty
  owa-cal create --subject "lunsj" --start 11:00 --end 11:30 --category "CC LUNCH"
  owa-cal create --subject "Standup" --date tomorrow --start 09:00 --end 09:30
  owa-cal update --id AAMkAG... --category "ProjectX"
  owa-cal delete --id AAMkAG...
  owa-cal categories""")


def _require_value(flag, args):
    if not args:
        _error(f'{flag} requires a value')
        sys.exit(1)
    return args[0], args[1:]


def _require_int(flag, args):
    v, args = _require_value(flag, args)
    try:
        return int(v), args
    except ValueError:
        _error(f'{flag} requires an integer, got: {v}')
        sys.exit(1)


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

def cmd_events(args, config, access_token, api_base):
    date_ = from_ = to_ = search = ''
    week = year = 0
    pretty = False
    limit = 50

    while args:
        flag, args = args[0], args[1:]
        if flag == '--date':
            v, args = _require_value(flag, args); date_ = resolve_date(v)
        elif flag == '--from':
            v, args = _require_value(flag, args); from_ = resolve_date(v)
        elif flag == '--to':
            v, args = _require_value(flag, args); to_ = resolve_date(v)
        elif flag == '--week':
            week, args = _require_int(flag, args)
        elif flag == '--year':
            year, args = _require_int(flag, args)
        elif flag == '--search':
            search, args = _require_value(flag, args)
        elif flag == '--pretty':
            pretty = True
        elif flag == '--limit':
            limit, args = _require_int(flag, args)
        else:
            _error(f'Unknown flag: {flag}'); sys.exit(1)

    if week:
        year = year or current_iso_week()[1]
        from_, to_ = iso_week_range(week, year)
    elif date_:
        from_ = to_ = date_
    elif not from_:
        from_ = to_ = today()
    if not to_:
        to_ = from_

    start_dt = f'{from_}T00:00:00'
    end_dt = f'{to_}T23:59:59'

    debug = _debug_enabled(config)
    if debug:
        print(f'DEBUG: events {from_} to {to_}', file=sys.stderr)

    select_fields = _EVENTS_SELECT
    orderby_field = _EVENTS_ORDERBY

    q = api_mod.build_query({
        'startDateTime': start_dt,
        'endDateTime': end_dt,
        '$top': limit,
        '$orderby': orderby_field,
        '$select': select_fields,
    })
    data = api_mod.api_get(api_base, f'me/calendarView?{q}', access_token, debug=debug)

    if data is None:
        return 1
    normalized = events_mod.normalize_events(data)
    if search:
        needle = search.lower()
        normalized = [
            e for e in normalized
            if needle in (e.get('subject') or '').lower()
        ]
    if pretty:
        print(format_events_pretty(normalized))
    else:
        print(json.dumps(normalized))
    return 0


def cmd_create(args, config, access_token, api_base):
    subject = date_ = start_time = end_time = category = location = body_text = showas = ''
    allday = False
    while args:
        flag, args = args[0], args[1:]
        if flag == '--subject':
            subject, args = _require_value(flag, args)
        elif flag == '--date':
            v, args = _require_value(flag, args); date_ = resolve_date(v)
        elif flag == '--start':
            start_time, args = _require_value(flag, args)
        elif flag == '--end':
            end_time, args = _require_value(flag, args)
        elif flag == '--category':
            category, args = _require_value(flag, args)
        elif flag == '--location':
            location, args = _require_value(flag, args)
        elif flag == '--body':
            body_text, args = _require_value(flag, args)
        elif flag == '--allday':
            allday = True
        elif flag == '--showas':
            showas, args = _require_value(flag, args)
        else:
            _error(f'Unknown flag: {flag}'); sys.exit(1)

    if not subject:
        _error('--subject is required'); sys.exit(1)
    date_ = date_ or today()
    if allday:
        start_dt = make_datetime(date_, '00:00')
        end_dt = make_datetime(_add_days(date_, 1), '00:00')
    else:
        start_time = start_time or '09:00'
        end_time = end_time or '10:00'
        start_dt = make_datetime(date_, start_time)
        end_dt = make_datetime(date_, end_time)

    tz = config.get('default_timezone') or config_mod.DEFAULT_TIMEZONE
    debug = _debug_enabled(config)
    body = events_mod.build_event_json(
        subject, start_dt, end_dt, tz,
        category=category, location=location, body_text=body_text,
        allday=allday, showas=showas,
    )
    if debug:
        print(f'DEBUG: creating event: {json.dumps(body)[:500]}', file=sys.stderr)
    result = api_mod.api_request('POST', api_base, 'me/events', access_token, body=body, debug=debug)
    if not result:
        return 1
    created = events_mod.normalize_event(result)
    print(json.dumps(created))
    _check_duplicates(created, date_, access_token, api_base, debug)
    return 0


def _check_duplicates(created, check_date, access_token, api_base, debug):
    """Post-create: warn if another event with the same subject/time
    already existed that day. Best-effort; failures are swallowed."""
    select_fields = 'Id,Subject,Start,End'
    q = api_mod.build_query({
        'startDateTime': f'{check_date}T00:00:00',
        'endDateTime': f'{check_date}T23:59:59',
        '$top': 50,
        '$orderby': _EVENTS_ORDERBY,
        '$select': select_fields,
    })
    existing = api_mod.api_get(api_base, f'me/calendarView?{q}', access_token, debug=debug)
    if not existing:
        return
    dupes = [
        e for e in events_mod.normalize_events(existing)
        if e.get('id') != created.get('id')
        and e.get('subject') == created.get('subject')
        and e.get('start') == created.get('start')
        and e.get('end') == created.get('end')
    ]
    if dupes:
        msg = (
            f'\033[33m⚠ Warning: Found {len(dupes)} other event(s) with same '
            f'subject/time on {check_date}. Possible duplicates.\033[0m'
        )
        print(msg, file=sys.stderr)


def cmd_update(args, config, access_token, api_base):
    event_id = ''
    fields = {}
    date_ = start_time = end_time = ''
    while args:
        flag, args = args[0], args[1:]
        if flag == '--id':
            event_id, args = _require_value(flag, args)
        elif flag == '--subject':
            fields['subject'], args = _require_value(flag, args)
        elif flag == '--category':
            fields['category'], args = _require_value(flag, args)
        elif flag == '--location':
            fields['location'], args = _require_value(flag, args)
        elif flag == '--body':
            fields['body'], args = _require_value(flag, args)
        elif flag == '--showas':
            fields['showas'], args = _require_value(flag, args)
        elif flag == '--date':
            v, args = _require_value(flag, args); date_ = resolve_date(v)
        elif flag == '--start':
            start_time, args = _require_value(flag, args)
        elif flag == '--end':
            end_time, args = _require_value(flag, args)
        else:
            _error(f'Unknown flag: {flag}'); sys.exit(1)

    if not event_id:
        _error('--id is required'); sys.exit(1)

    debug = _debug_enabled(config)

    if start_time or end_time or date_:
        # Merge against existing event so partial date/time edits do not
        # clobber the other half of the range.
        existing_raw = api_mod.api_get(api_base, _event_path(event_id), access_token, debug=debug)
        if not existing_raw:
            return 1
        existing = events_mod.normalize_event(existing_raw)
        existing_start = existing.get('start') or ''
        existing_end = existing.get('end') or ''
        existing_start_date, existing_start_time = _split_datetime(existing_start)
        existing_end_date, existing_end_time = _split_datetime(existing_end)
        patch_start_date = date_ or existing_start_date
        patch_end_date = existing_end_date or patch_start_date
        if date_:
            patch_end_date = _add_days(
                date_, _date_delta_days(existing_start_date, existing_end_date)
            )
        if start_time:
            fields['start'] = make_datetime(patch_start_date, start_time)
        elif date_:
            fields['start'] = make_datetime(patch_start_date, existing_start_time)
        if end_time:
            fields['end'] = make_datetime(patch_end_date, end_time)
        elif date_:
            fields['end'] = make_datetime(patch_end_date, existing_end_time)

    if not fields:
        _error(
            'update requires at least one field '
            '(--subject, --category, --location, --body, --showas, '
            '--date, --start, --end)'
        )
        return 1

    tz = config.get('default_timezone') or config_mod.DEFAULT_TIMEZONE
    patch = events_mod.build_patch_json(fields, tz)
    result = api_mod.api_request('PATCH', api_base, _event_path(event_id), access_token, body=patch, debug=debug)
    if not result:
        return 1
    print(json.dumps(events_mod.normalize_event(result)))
    return 0


def cmd_delete(args, config, access_token, api_base):
    event_id = ''
    confirm = False
    while args:
        flag, args = args[0], args[1:]
        if flag == '--id':
            event_id, args = _require_value(flag, args)
        elif flag == '--confirm':
            confirm = True
        else:
            _error(f'Unknown flag: {flag}'); sys.exit(1)
    if not event_id:
        _error('--id is required'); sys.exit(1)

    debug = _debug_enabled(config)

    if not confirm:
        existing_raw = api_mod.api_get(api_base, _event_path(event_id), access_token, debug=debug)
        if not existing_raw:
            return 1
        existing = events_mod.normalize_event(existing_raw)
        sys.stderr.write(
            f"\033[33mDelete '{existing.get('subject','')}' ({existing.get('start','')})? (y/N): \033[0m"
        )
        sys.stderr.flush()
        try:
            answer = input().strip().lower()
        except EOFError:
            answer = ''
        if answer not in ('y', 'yes'):
            _info('Aborted.')
            return 0

    result = api_mod.api_request('DELETE', api_base, _event_path(event_id), access_token, debug=debug)
    if result is None:
        return 1
    _info('Deleted.')
    return 0


def cmd_categories(args, config, access_token, api_base):
    add = ''
    pretty = False
    while args:
        flag, args = args[0], args[1:]
        if flag == '--add':
            add, args = _require_value(flag, args)
        elif flag == '--pretty':
            pretty = True
        else:
            _error(f'Unknown flag: {flag}'); sys.exit(1)

    debug = _debug_enabled(config)
    # Outlook REST v2.0 exposes master categories at `me/MasterCategories`.
    # The Graph equivalent (`me/outlook/masterCategories`) is NOT reachable
    # here - see auth.py for why the owa-piggy token lacks Graph calendar
    # scopes. Using the Graph path yields `RequestBroker--ParseUri:
    # Resource not found for the segment 'outlook'`.
    cat_path = 'me/MasterCategories'

    if add:
        body = {'DisplayName': add, 'Color': 'Preset0'}
        result = api_mod.api_request('POST', api_base, cat_path, access_token, body=body, debug=debug)
        if not result:
            return 1
        print(json.dumps(result))
        return 0

    data = api_mod.api_get(api_base, cat_path, access_token, debug=debug)
    if data is None:
        return 1
    items = [
        {'name': c.get('DisplayName') or '', 'color': c.get('Color') or ''}
        for c in data.get('value', [])
    ]
    if pretty:
        if items:
            width = max(len(i['name']) for i in items)
            for i in items:
                print(f"{i['name']:<{width}}  {i['color']}")
        return 0
    print(json.dumps(items))
    return 0


def cmd_config(args, config):
    """Handled specially: no auth required, so this does not call
    setup_auth - the dispatcher routes `config` here before auth."""
    profile = ''
    while args:
        flag, args = args[0], args[1:]
        if flag == '--profile':
            profile, args = _require_value(flag, args)
        else:
            _error(f'Unknown flag: {flag}'); sys.exit(1)

    if profile:
        config_mod.config_set('owa_piggy_profile', profile)
        _info(f'owa-piggy profile saved: {profile}')
        return 0

    _info(f'Config file: {config_mod.CONFIG_PATH}')
    if config.get('owa_piggy_profile'):
        _info(f"  owa_piggy_profile={config.get('owa_piggy_profile')}")
    else:
        _info('  owa_piggy_profile=(not set - owa-piggy picks its default)')
    _info(f"  default_timezone={config.get('default_timezone')}")
    return 0


def cmd_refresh(args, config):
    if args:
        _error(f'Unknown flag: {args[0]}'); sys.exit(1)
    _info('Refreshing token...')
    access = auth_mod.do_token_refresh(config, debug=_debug_enabled(config))
    if not access:
        _error('Token refresh failed.')
        return 1
    me = api_mod.api_get(
        'https://outlook.office.com/api/v2.0', 'me', access,
        debug=_debug_enabled(config),
    )
    if not isinstance(me, dict):
        _error('Auth verification failed.')
        return 1
    name = me.get('DisplayName') or me.get('displayName')
    if name:
        _info(f'Authenticated as {name}')
    return 0


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

AUTHED_COMMANDS = {'events', 'create', 'update', 'delete', 'categories'}


def main():
    argv = sys.argv[1:]

    if not argv:
        print_help()
        return 0
    if argv[0] in ('help', '--help', '-h'):
        print_help()
        return 0

    debug_flag = False
    profile_override = ''
    # Strip global flags (--debug/--verbose, --profile) from anywhere in
    # argv. Exception: on `owa-cal config`, --profile is a subcommand
    # flag that writes to the config file, so leave it in place.
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
        _error(f"Unknown command: {cmd}. Run 'owa-cal help' for usage.")
        return 1

    access_token, api_base = auth_mod.setup_auth(
        config, debug=_debug_enabled(config)
    )

    if cmd == 'events':
        return cmd_events(rest, config, access_token, api_base)
    if cmd == 'create':
        return cmd_create(rest, config, access_token, api_base)
    if cmd == 'update':
        return cmd_update(rest, config, access_token, api_base)
    if cmd == 'delete':
        return cmd_delete(rest, config, access_token, api_base)
    if cmd == 'categories':
        return cmd_categories(rest, config, access_token, api_base)

    # Unreachable: AUTHED_COMMANDS guarded above.
    return 1
