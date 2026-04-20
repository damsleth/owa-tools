"""Argument parsing and dispatch for the `cal-cli` command.

cal-cli is pipe-friendly: JSON on stdout, logs on stderr. --pretty
switches stdout to a human-readable table. Exit codes follow POSIX
convention (0 success, 1 error).

Subcommands are parsed manually (no argparse subparsers) to keep the
code flat and to match the old zsh dispatch exactly. Each cmd_* fn is
responsible for its own flag loop.
"""
import json
import os
import sys

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


def _error(msg):
    print(f'ERROR: {msg}', file=sys.stderr)


def _info(msg):
    print(msg, file=sys.stderr)


def _debug_enabled(config):
    return bool(config.get('debug')) or os.environ.get('CAL_DEBUG') == '1'


def print_help():
    """cal-cli help output. Kept verbatim to the zsh version so muscle
    memory still works."""
    print("""cal-cli - Calendar CLI for Outlook / Microsoft 365

Usage: cal-cli <command> [options]

Global options:
  --debug, --verbose  Print HTTP requests and response bodies on errors
                      (also: CAL_DEBUG=1)

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
  --refresh-token <v> Set MSAL refresh token
  --tenant-id <id>    Set Azure AD tenant ID
  --app-client-id <id> Set app registration client ID (optional)

Auth:
  Requires OUTLOOK_REFRESH_TOKEN + OUTLOOK_TENANT_ID.
  Set via env vars or ~/.config/cal-cli/config (env wins).

  If OUTLOOK_APP_CLIENT_ID is set, uses that app registration directly
  (standard OAuth2 refresh_token grant).

  Otherwise falls back to owa-piggy (brew install damsleth/tap/owa-piggy),
  which piggybacks on OWA's public SPA client - no app registration needed.

  Quickstart (owa-piggy):
    brew install damsleth/tap/owa-piggy
    owa-piggy --setup
    cal-cli config --refresh-token "$(owa-piggy --json | jq -r .refresh_token)" \\
                   --tenant-id "$(owa-piggy --json | jq -r .tenant_id)"

Examples:
  cal-cli events --pretty
  cal-cli events --week 16 --pretty
  cal-cli events --from 2026-04-14 --to 2026-04-18 --pretty
  cal-cli create --subject "lunsj" --start 11:00 --end 11:30 --category "CC LUNCH"
  cal-cli create --subject "Standup" --date tomorrow --start 09:00 --end 09:30
  cal-cli update --id AAMkAG... --category "ProjectX"
  cal-cli delete --id AAMkAG...
  cal-cli categories""")


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

def cmd_events(args, config, access_token, api_base, api_case):
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

    if api_case == 'camel':
        select_fields = 'id,subject,start,end,location,categories,showAs,isAllDay,originalStartTimeZone,originalEndTimeZone'
        orderby_field = 'start/dateTime'
        filter_field = 'subject'
    else:
        select_fields = 'Id,Subject,Start,End,Location,Categories,ShowAs,IsAllDay,OriginalStartTimeZone,OriginalEndTimeZone'
        orderby_field = 'Start/DateTime'
        filter_field = 'Subject'

    if search:
        safe = search.replace("'", "''")
        q = api_mod.build_query({
            '$filter': f"contains({filter_field},'{safe}')",
            '$top': limit,
            '$orderby': orderby_field,
            '$select': select_fields,
        })
        data = api_mod.api_get(api_base, f'me/events?{q}', access_token, debug=debug)
    else:
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
    if pretty:
        print(format_events_pretty(normalized))
    else:
        print(json.dumps(normalized))
    return 0


def cmd_create(args, config, access_token, api_base, api_case):
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
    start_time = start_time or '09:00'
    end_time = end_time or '10:00'
    start_dt = make_datetime(date_, start_time)
    end_dt = make_datetime(date_, end_time)

    tz = config.get('default_timezone') or config_mod.DEFAULT_TIMEZONE
    debug = _debug_enabled(config)
    body = events_mod.build_event_json(
        subject, start_dt, end_dt, tz,
        category=category, location=location, body_text=body_text,
        allday=allday, showas=showas, api_case=api_case,
    )
    if debug:
        print(f'DEBUG: creating event: {json.dumps(body)[:500]}', file=sys.stderr)
    result = api_mod.api_request('POST', api_base, 'me/events', access_token, body=body, debug=debug)
    if not result:
        return 1
    created = events_mod.normalize_event(result)
    print(json.dumps(created))
    _check_duplicates(created, date_, access_token, api_base, api_case, debug)
    return 0


def _check_duplicates(created, check_date, access_token, api_base, api_case, debug):
    """Post-create: warn if another event with the same subject/time
    already existed that day. Best-effort; failures are swallowed."""
    if api_case == 'camel':
        select_fields = 'id,subject,start,end'
        orderby_field = 'start/dateTime'
    else:
        select_fields = 'Id,Subject,Start,End'
        orderby_field = 'Start/DateTime'
    q = api_mod.build_query({
        'startDateTime': f'{check_date}T00:00:00',
        'endDateTime': f'{check_date}T23:59:59',
        '$top': 50,
        '$orderby': orderby_field,
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


def cmd_update(args, config, access_token, api_base, api_case):
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
        existing_raw = api_mod.api_get(api_base, f'me/events/{event_id}', access_token, debug=debug)
        if not existing_raw:
            return 1
        existing = events_mod.normalize_event(existing_raw)
        existing_start = existing.get('start') or ''
        existing_end = existing.get('end') or ''
        existing_date = existing_start.split('T')[0] if 'T' in existing_start else ''
        existing_start_time = existing_start.split('T')[1] if 'T' in existing_start else ''
        existing_end_time = existing_end.split('T')[1] if 'T' in existing_end else ''
        patch_date = date_ or existing_date
        if start_time:
            fields['start'] = make_datetime(patch_date, start_time)
        elif date_:
            fields['start'] = make_datetime(patch_date, existing_start_time)
        if end_time:
            fields['end'] = make_datetime(patch_date, end_time)
        elif date_:
            fields['end'] = make_datetime(patch_date, existing_end_time)

    if not fields:
        _error(
            'update requires at least one field '
            '(--subject, --category, --location, --body, --showas, '
            '--date, --start, --end)'
        )
        return 1

    tz = config.get('default_timezone') or config_mod.DEFAULT_TIMEZONE
    patch = events_mod.build_patch_json(fields, tz, api_case=api_case)
    result = api_mod.api_request('PATCH', api_base, f'me/events/{event_id}', access_token, body=patch, debug=debug)
    if not result:
        return 1
    print(json.dumps(events_mod.normalize_event(result)))
    return 0


def cmd_delete(args, config, access_token, api_base, api_case):
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
        existing_raw = api_mod.api_get(api_base, f'me/events/{event_id}', access_token, debug=debug)
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

    result = api_mod.api_request('DELETE', api_base, f'me/events/{event_id}', access_token, debug=debug)
    if result is None:
        return 1
    _info('Deleted.')
    return 0


def cmd_categories(args, config, access_token, api_base, api_case):
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
    # Outlook REST v2.0 exposes master categories at `me/MasterCategories`;
    # Graph puts them under `me/outlook/masterCategories`. Hitting the Graph
    # path against Outlook REST yields `RequestBroker--ParseUri: Resource
    # not found for the segment 'outlook'`.
    if api_case == 'camel':
        cat_path = 'me/outlook/masterCategories'
        body_key_name, body_key_color = 'displayName', 'color'
        preset = 'preset0'
    else:
        cat_path = 'me/MasterCategories'
        body_key_name, body_key_color = 'DisplayName', 'Color'
        preset = 'Preset0'

    if add:
        body = {body_key_name: add, body_key_color: preset}
        result = api_mod.api_request('POST', api_base, cat_path, access_token, body=body, debug=debug)
        if not result:
            return 1
        print(json.dumps(result))
        return 0

    data = api_mod.api_get(api_base, cat_path, access_token, debug=debug)
    if data is None:
        return 1
    # Normalize pascal/camel so consumers get a stable shape.
    items = [
        {
            'name': c.get('DisplayName') or c.get('displayName') or '',
            'color': c.get('Color') or c.get('color') or '',
        }
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


def cmd_config(args, config, access_token=None, api_base=None, api_case=None):
    """Handled specially: no auth required, so access_token/api_base
    are optional. Called in both modes via the main dispatcher."""
    refresh_token = tenant_id = app_client_id = ''
    while args:
        flag, args = args[0], args[1:]
        if flag == '--refresh-token':
            refresh_token, args = _require_value(flag, args)
        elif flag == '--tenant-id':
            tenant_id, args = _require_value(flag, args)
        elif flag == '--app-client-id':
            app_client_id, args = _require_value(flag, args)
        else:
            _error(f'Unknown flag: {flag}'); sys.exit(1)

    wrote = False
    if refresh_token:
        config_mod.config_set('OUTLOOK_REFRESH_TOKEN', refresh_token)
        _info('Refresh token saved'); wrote = True
    if tenant_id:
        config_mod.config_set('OUTLOOK_TENANT_ID', tenant_id)
        _info('Tenant ID saved'); wrote = True
    if app_client_id:
        config_mod.config_set('OUTLOOK_APP_CLIENT_ID', app_client_id)
        _info('App client ID saved'); wrote = True

    if not wrote:
        _info(f'Config file: {config_mod.CONFIG_PATH}')
        if config.get('OUTLOOK_REFRESH_TOKEN'):
            _info(f"  OUTLOOK_REFRESH_TOKEN=set (tenant: {config.get('OUTLOOK_TENANT_ID','not set')})")
        else:
            _info('  OUTLOOK_REFRESH_TOKEN=(not set)')
        if config.get('OUTLOOK_APP_CLIENT_ID'):
            _info(f"  OUTLOOK_APP_CLIENT_ID={config.get('OUTLOOK_APP_CLIENT_ID')} (app registration)")
        else:
            _info('  OUTLOOK_APP_CLIENT_ID=(not set - using owa-piggy)')
        _info(f"  default_timezone={config.get('default_timezone')}")
    return 0


def cmd_refresh(args, config):
    if args:
        _error(f'Unknown flag: {args[0]}'); sys.exit(1)
    if not config.get('OUTLOOK_REFRESH_TOKEN') or not config.get('OUTLOOK_TENANT_ID'):
        _error(
            f'OUTLOOK_REFRESH_TOKEN and OUTLOOK_TENANT_ID must be set '
            f'(via env or {config_mod.CONFIG_PATH})'
        )
        return 1
    _info('Refreshing token...')
    access = auth_mod.do_token_refresh(config, debug=_debug_enabled(config))
    if not access:
        _error('Token refresh failed.')
        return 1
    me = api_mod.api_get('https://outlook.office.com/api/v2.0', 'me', access)
    if isinstance(me, dict):
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
    debug_flag = False
    filtered = []
    for a in argv:
        if a in ('--debug', '--verbose'):
            debug_flag = True
        else:
            filtered.append(a)
    argv = filtered

    if not argv:
        print_help()
        return 0

    cmd, rest = argv[0], argv[1:]

    if cmd in ('help', '--help', '-h'):
        print_help()
        return 0

    config = config_mod.load_config()
    if debug_flag:
        config['debug'] = True
        _info('DEBUG: verbose logging enabled')

    if cmd == 'config':
        return cmd_config(rest, config)
    if cmd == 'refresh':
        return cmd_refresh(rest, config)

    if cmd not in AUTHED_COMMANDS:
        _error(f"Unknown command: {cmd}. Run 'cal-cli help' for usage.")
        return 1

    access_token, api_base, api_case = auth_mod.setup_auth(
        config, debug=_debug_enabled(config)
    )

    if cmd == 'events':
        return cmd_events(rest, config, access_token, api_base, api_case)
    if cmd == 'create':
        return cmd_create(rest, config, access_token, api_base, api_case)
    if cmd == 'update':
        return cmd_update(rest, config, access_token, api_base, api_case)
    if cmd == 'delete':
        return cmd_delete(rest, config, access_token, api_base, api_case)
    if cmd == 'categories':
        return cmd_categories(rest, config, access_token, api_base, api_case)

    # Unreachable: AUTHED_COMMANDS guarded above.
    return 1
