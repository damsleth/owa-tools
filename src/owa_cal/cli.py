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

from owa_core import modes as mode_mod
from owa_core import periods as periods_mod
from owa_core import schema as schema_mod
from owa_core import tty as tty_mod
from owa_core.errors import UsageError, _require_value, emit_error, emit_message

from . import __version__
from . import api as api_mod
from . import auth as auth_mod
from . import config as config_mod
from . import events as events_mod
from . import ics as ics_mod
from . import profiles as profiles_mod
from .dates import (
    iso_week_range,
    make_datetime,
    today,
)
from .format import format_events_pretty

# OData $select / $orderby fragments shared by `events` listing and the
# post-create duplicate check. Keep these in sync: the dupe check
# compares the same normalized fields the listing surfaces.
_EVENTS_SELECT = (
    'Id,Subject,Start,End,Location,Categories,ShowAs,IsAllDay,'
    'OriginalStartTimeZone,OriginalEndTimeZone,Type,SeriesMasterId'
)
_EVENTS_ORDERBY = 'Start/DateTime'

# Fields fetched by `show --id` to populate normalize_event_detail:
# the base event fields plus the heavier attendee/organizer/body fields
# that calendarView omits by default.
_DETAIL_SELECT = (
    'Id,Subject,Start,End,Location,Categories,ShowAs,IsAllDay,'
    'Organizer,IsOrganizer,Attendees,ResponseStatus,BodyPreview'
)


def _error(msg):
    emit_message(msg)


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
  --profile <alias>   Profile alias for this invocation. Resolves to a
                      local webcal source first (see `profiles add`),
                      else forwarded to owa-piggy as --profile <alias>.
                      Overrides owa_piggy_profile in the config file
                      and OWA_PROFILE in the env.

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
  OWA_CAL_WEBCAL_URL  Ad-hoc webcal/iCal source (no profile). Used only
                      when no --profile name is set. Read-only: `events`
                      works, write commands fail cleanly.

Commands:
  refresh             Force a token refresh and verify auth
  events              List calendar events (default: today)
  create              Create a new event
  update              Update an existing event
  delete              Delete an event
  respond             Accept/decline/tentatively-accept a meeting invite
  categories          List or add master categories
  profiles            List/add/delete calendar profiles (merged with
                      owa-piggy profiles)
  config              View or update configuration
  help                Show this help

Events options:
  --date <date>       Specific day. YYYY-MM-DD, today/tomorrow/yesterday,
                      a signed day offset (+1, -3), or a weekday name in the
                      current ISO week with optional week offset
                      (monday, monday+1, friday-2)
  --from <date>       Start of range (same vocabulary as --date)
  --to <date>         End of range (same vocabulary as --date)
  --week <n|rel>      ISO week: a number (16), current/last/next, or +n/-n
  --month <n|rel>     Calendar month: 1-12, current/last/next, or +n/-n
                      (default when given without value: current)
  --year <n|rel>      Year: a full year (2026), current/last/next, or +n/-n.
                      Combine with --week/--month, or use alone for the
                      whole year
  --search <term>     Search events by subject
  --pretty            Human-readable table (default: JSON)
  --limit <n>         Max results per page (default 50, cap 200)
  --all               Follow @odata.nextLink until exhausted (--limit
                      still controls page size per request)

Create options:
  --subject <title>   Event title (required)
  --date <date>       Date (default: today)
  --start <HH:MM>     Start time (default: 09:00)
  --end <HH:MM>       End time (default: 10:00)
  --category <name>   Category name (repeatable)
  --attendee <email>  Required attendee (repeatable)
  --optional-attendee <email>
                      Optional attendee (repeatable)
  --reminder <min>    Reminder minutes before start (turns the reminder on)
  --recur <daily|weekly>
                      Recurrence pattern (anchored on the event's start day;
                      weekly repeats on that weekday)
  --recur-interval <n>  Every n days/weeks (default 1)
  --recur-count <n>     End after n occurrences
  --recur-until <date>  End on YYYY-MM-DD (mutually exclusive with --recur-count)
  --location <place>  Location
  --body <text>       Description
  --allday            All-day event
  --showas <status>   busy, free, tentative, oof

Update options:
  --id <event-id>     Event ID (required)
  --subject, --date, --start, --end, --category, --attendee,
  --optional-attendee, --reminder, --recur, --recur-interval,
  --recur-count, --recur-until, --location, --body, --showas
  (--category/--attendee/--optional-attendee replace the existing set)

Delete options:
  --id <event-id>     Event ID (required)
  --confirm           Skip confirmation prompt

Respond options:
  --id <event-id>     Event ID (required)
  --action <action>   accept, decline, or tentative (required)
  --comment <text>    Optional note sent to the organizer
  --no-notify         Record the response without notifying the organizer

Categories options:
  --add <name>        Add a new master category
  --pretty            Human-readable table (default: JSON)
  (no flags)          List all categories as JSON

Profiles options:
  profiles                       List all profiles as JSON (owa-cal +
                                 owa-piggy, with shadow markers)
  profiles --pretty              Human-readable listing
  profiles add <alias> --webcal <url>
                                 Save a webcal/iCal source under <alias>.
                                 The URL is a bearer secret stored at
                                 ~/.config/owa-cal/profiles.json (0600).
  profiles delete <alias>        Remove an owa-cal profile

Config options:
  --profile <alias>   Pin a default profile alias (owa_piggy_profile)

Auth:
  owa-cal shells out to owa-piggy for a fresh access token on every
  call. owa-piggy owns the token lifecycle; owa-cal stores nothing
  more than an optional profile alias.

  Quickstart:
    brew install damsleth/tap/owa-piggy
    owa-piggy setup                           # or: setup --profile work

Events carry opaque ids: address one via --id or as a bare positional
argument (`owa-cal delete <id>` == `owa-cal delete --id <id>`).

Examples:
  owa-cal events --pretty
  owa-cal events --week 16 --pretty
  owa-cal events --week last --pretty          # previous ISO week
  owa-cal events --week next                   # same as --week +1
  owa-cal events --month --pretty              # this calendar month
  owa-cal events --month next                  # next month
  owa-cal events --year +1 --pretty            # whole next year
  owa-cal events --date monday+1               # next Monday
  owa-cal events --from 2026-04-14 --to 2026-04-18 --pretty
  owa-cal create --subject "lunsj" --start 11:00 --end 11:30 --category "CC LUNCH"
  owa-cal create --subject "Standup" --date tomorrow --start 09:00 --end 09:30
  owa-cal update --id AAMkAG... --category "ProjectX"
  owa-cal delete --id AAMkAG...
  owa-cal respond --id AAMkAG... --action accept
  owa-cal respond --id AAMkAG... --action decline --comment "conflict"
  owa-cal categories
  owa-cal profiles --pretty
  owa-cal profiles add brkh --webcal 'https://example.invalid/feed?key=...'
  owa-cal --profile brkh events --pretty""")
    print()
    print(schema_mod.MULTI_PROFILE_HELP)
    print()
    print(schema_mod.MACHINE_SURFACE_HELP)


def _optional_value(args, default):
    """Consume the next token as a value unless it is missing or is another
    flag (`--xxx`), in which case return `default` and leave args untouched.
    Lets bare `--month` mean the current month while `--month next` and
    `--month -1` still work (signed offsets are values, not flags, because
    every owa-cal flag is double-dashed)."""
    if args and not args[0].startswith('--'):
        return args[0], args[1:]
    return default, args


def _require_int(flag, args):
    v, args = _require_value(flag, args)
    try:
        return int(v), args
    except ValueError:
        raise UsageError(f'{flag} requires an integer, got: {v}')


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

def _resolve_event_window(date_, from_, to_, week, month, year):
    """Resolve listing flags to an inclusive (from, to) date range.

    Delegates to the shared owa_core.periods resolver, supplying owa-cal's
    Mon-Sun week shape. Accepts the full relative/semantic vocabulary
    (current/last/next/+n/-n for --week/--month/--year, weekday names and
    offsets for --date). Conflicting period flags raise UsageError.
    """
    return periods_mod.resolve_window(
        iso_week_range=iso_week_range,
        date_=date_, from_=from_, to_=to_,
        week=week, month=month, year=year,
    )


def cmd_events_webcal(args, config):
    """Read-only events listing from a webcal/iCal feed.

    Accepts the same range/search/pretty flags as `cmd_events` but
    talks to a published feed instead of Outlook REST. Filters are
    applied client-side after fetch (a small feed makes this cheap;
    `--limit` is also enforced here).
    """
    date_ = from_ = to_ = search = ''
    week = month = year = ''
    pretty = False
    limit = 50
    while args:
        flag, args = args[0], args[1:]
        if flag == '--date':
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
        elif flag == '--search':
            search, args = _require_value(flag, args)
        elif flag == '--pretty':
            pretty = True
        elif flag == '--all':
            # The webcal feed is fetched in full client-side, so it is
            # already "all pages"; accept the flag as a no-op for parity
            # with the Outlook REST path.
            pass
        elif flag == '--limit':
            limit, args = _require_int(flag, args)
            limit = max(1, min(limit, 200))
        else:
            raise UsageError(f'Unknown flag: {flag}')

    from_, to_ = _resolve_event_window(date_, from_, to_, week, month, year)

    debug = _debug_enabled(config)
    url = (config.get('webcal_url') or '').strip()
    if debug:
        print(f'DEBUG: webcal events {from_} to {to_} <- {url}', file=sys.stderr)
    try:
        events = ics_mod.fetch_and_normalize(url)
    except ics_mod.FetchError as exc:
        _error(f'failed to fetch webcal feed: {exc}')
        return 1
    events = ics_mod.filter_by_range(events, from_, to_)
    events = ics_mod.filter_by_subject(events, search)
    events.sort(key=lambda e: e.get('start') or '')
    events = events[:limit]
    if pretty:
        print(format_events_pretty(events))
    else:
        print(json.dumps(events))
    return 0


def cmd_events(args, config, access_token, api_base):
    date_ = from_ = to_ = search = ''
    week = month = year = ''
    pretty = False
    all_pages = False
    limit = 50

    while args:
        flag, args = args[0], args[1:]
        if flag == '--date':
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
        elif flag == '--search':
            search, args = _require_value(flag, args)
        elif flag == '--pretty':
            pretty = True
        elif flag == '--all':
            all_pages = True
        elif flag == '--limit':
            limit, args = _require_int(flag, args)
            limit = max(1, min(limit, 200))
        else:
            raise UsageError(f'Unknown flag: {flag}')

    from_, to_ = _resolve_event_window(date_, from_, to_, week, month, year)

    start_dt = f'{from_}T00:00:00'
    end_dt = f'{to_}T23:59:59'

    debug = _debug_enabled(config)
    if debug:
        print(f'DEBUG: events {from_} to {to_}', file=sys.stderr)

    select_fields = _EVENTS_SELECT
    orderby_field = _EVENTS_ORDERBY

    # --limit still controls page size ($top per request); --all follows
    # @odata.nextLink until every page is exhausted.
    q = api_mod.build_query({
        'startDateTime': start_dt,
        'endDateTime': end_dt,
        '$top': limit,
        '$orderby': orderby_field,
        '$select': select_fields,
    })
    # Render event times in the configured timezone so calendarView's
    # window edges line up with the user's day (fixes an off-by-one where
    # Outlook's default UTC rendering shifted events across midnight).
    tz = config.get('default_timezone') or config_mod.DEFAULT_TIMEZONE
    prefer_headers = {'Prefer': f'outlook.timezone="{tz}"'}
    if all_pages:
        items = api_mod.paginate_all(
            api_base, f'me/calendarView?{q}', access_token,
            debug=debug, headers=prefer_headers,
        )
        if items is None:
            return 1
        data = {'value': items}
    else:
        data = api_mod.api_get(
            api_base, f'me/calendarView?{q}', access_token,
            debug=debug, headers=prefer_headers,
        )
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


def cmd_show(args, config, access_token, api_base):
    """Fetch a single event by id and emit its full detail via normalize_event_detail.

    Requests the detail-select fields (Organizer, Attendees, ResponseStatus,
    BodyPreview) that calendarView omits, then routes the response through
    normalize_event_detail so attendees, organizer, and body are reachable.
    """
    event_id, args = schema_mod.pop_positional_id(args)
    while args:
        flag, args = args[0], args[1:]
        if flag == '--id':
            event_id, args = _require_value(flag, args)
        else:
            raise UsageError(f'Unknown flag: {flag}')

    if not event_id:
        raise UsageError('--id is required')

    debug = _debug_enabled(config)
    q = api_mod.build_query({'$select': _DETAIL_SELECT})
    raw = api_mod.api_get(api_base, f'{_event_path(event_id)}?{q}', access_token, debug=debug)
    if raw is None:
        return 1
    print(json.dumps(events_mod.normalize_event_detail(raw)))
    return 0


def cmd_create(args, config, access_token, api_base):
    subject = date_ = start_time = end_time = location = body_text = showas = ''
    allday = False
    categories = []
    required_att = []
    optional_att = []
    reminder = None
    recur = recur_until = ''
    recur_interval = 1
    recur_count = 0
    while args:
        flag, args = args[0], args[1:]
        if flag == '--subject':
            subject, args = _require_value(flag, args)
        elif flag == '--date':
            v, args = _require_value(flag, args); date_ = periods_mod.resolve_day(v)
        elif flag == '--start':
            start_time, args = _require_value(flag, args)
        elif flag == '--end':
            end_time, args = _require_value(flag, args)
        elif flag == '--category':
            v, args = _require_value(flag, args); categories.append(v)
        elif flag == '--attendee':
            v, args = _require_value(flag, args); required_att.append(v)
        elif flag == '--optional-attendee':
            v, args = _require_value(flag, args); optional_att.append(v)
        elif flag == '--reminder':
            reminder, args = _require_int(flag, args)
        elif flag == '--recur':
            recur, args = _require_value(flag, args)
        elif flag == '--recur-interval':
            recur_interval, args = _require_int(flag, args)
        elif flag == '--recur-count':
            recur_count, args = _require_int(flag, args)
        elif flag == '--recur-until':
            recur_until, args = _require_value(flag, args)
        elif flag == '--location':
            location, args = _require_value(flag, args)
        elif flag == '--body':
            body_text, args = _require_value(flag, args)
        elif flag == '--allday':
            allday = True
        elif flag == '--showas':
            showas, args = _require_value(flag, args)
        else:
            raise UsageError(f'Unknown flag: {flag}')

    if not subject:
        raise UsageError('--subject is required')
    if recur_count and recur_until:
        raise UsageError('--recur-count and --recur-until are mutually exclusive')
    if (recur_interval != 1 or recur_count or recur_until) and not recur:
        raise UsageError('--recur-interval/--recur-count/--recur-until require --recur')
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
    attendees = events_mod.build_attendees(required_att, optional_att)
    try:
        recurrence = events_mod.build_recurrence(
            recur, date_, interval=recur_interval,
            count=recur_count, until=recur_until,
        )
    except ValueError as exc:
        raise UsageError(str(exc))
    body = events_mod.build_event_json(
        subject, start_dt, end_dt, tz,
        location=location, body_text=body_text,
        allday=allday, showas=showas,
        categories=categories, attendees=attendees,
        reminder=reminder, recurrence=recurrence,
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
    event_id, args = schema_mod.pop_positional_id(args)
    fields = {}
    date_ = start_time = end_time = ''
    categories = []
    required_att = []
    optional_att = []
    have_attendees = False
    recur = recur_until = ''
    recur_interval = 1
    recur_count = 0
    while args:
        flag, args = args[0], args[1:]
        if flag == '--id':
            event_id, args = _require_value(flag, args)
        elif flag == '--subject':
            fields['subject'], args = _require_value(flag, args)
        elif flag == '--category':
            v, args = _require_value(flag, args); categories.append(v)
        elif flag == '--attendee':
            v, args = _require_value(flag, args); required_att.append(v); have_attendees = True
        elif flag == '--optional-attendee':
            v, args = _require_value(flag, args); optional_att.append(v); have_attendees = True
        elif flag == '--reminder':
            fields['reminder'], args = _require_int(flag, args)
        elif flag == '--recur':
            recur, args = _require_value(flag, args)
        elif flag == '--recur-interval':
            recur_interval, args = _require_int(flag, args)
        elif flag == '--recur-count':
            recur_count, args = _require_int(flag, args)
        elif flag == '--recur-until':
            recur_until, args = _require_value(flag, args)
        elif flag == '--location':
            fields['location'], args = _require_value(flag, args)
        elif flag == '--body':
            fields['body'], args = _require_value(flag, args)
        elif flag == '--showas':
            fields['showas'], args = _require_value(flag, args)
        elif flag == '--date':
            v, args = _require_value(flag, args); date_ = periods_mod.resolve_day(v)
        elif flag == '--start':
            start_time, args = _require_value(flag, args)
        elif flag == '--end':
            end_time, args = _require_value(flag, args)
        else:
            raise UsageError(f'Unknown flag: {flag}')

    if not event_id:
        raise UsageError('--id is required')
    if recur_count and recur_until:
        raise UsageError('--recur-count and --recur-until are mutually exclusive')
    if (recur_interval != 1 or recur_count or recur_until) and not recur:
        raise UsageError('--recur-interval/--recur-count/--recur-until require --recur')
    if categories:
        fields['categories'] = categories
    if have_attendees:
        fields['attendees'] = events_mod.build_attendees(required_att, optional_att)

    debug = _debug_enabled(config)

    # Recurrence patterns anchor on the event's start date. Reuse the new
    # --date if given; otherwise fetch the existing event to read it.
    recur_anchor = date_
    if start_time or end_time or date_ or recur:
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
        recur_anchor = date_ or existing_start_date
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

    if recur:
        try:
            recurrence = events_mod.build_recurrence(
                recur, recur_anchor, interval=recur_interval,
                count=recur_count, until=recur_until,
            )
        except ValueError as exc:
            raise UsageError(str(exc))
        if recurrence:
            fields['recurrence'] = recurrence

    if not fields:
        _error(
            'update requires at least one field '
            '(--subject, --category, --location, --body, --showas, '
            '--date, --start, --end, --attendee, --optional-attendee, '
            '--reminder, --recur)'
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
    event_id, args = schema_mod.pop_positional_id(args)
    confirm = False
    while args:
        flag, args = args[0], args[1:]
        if flag == '--id':
            event_id, args = _require_value(flag, args)
        elif flag == '--confirm':
            confirm = True
        else:
            raise UsageError(f'Unknown flag: {flag}')
    if not event_id:
        raise UsageError('--id is required')

    debug = _debug_enabled(config)

    if not confirm:
        try:
            tty_mod.require_confirm_or_tty(action='delete event')
        except UsageError as error:
            return emit_error(error)
        existing_raw = api_mod.api_get(api_base, _event_path(event_id), access_token, debug=debug)
        if not existing_raw:
            return 1
        existing = events_mod.normalize_event(existing_raw)
        if not tty_mod.confirm(
            f"\033[33mDelete '{existing.get('subject','')}' ({existing.get('start','')})? (y/N): \033[0m"
        ):
            _info('Aborted.')
            return 0

    result = api_mod.api_request('DELETE', api_base, _event_path(event_id), access_token, debug=debug)
    if result is None:
        return 1
    _info('Deleted.')
    return 0


# Maps the user-facing --action value to the Outlook REST action segment.
# The three are the only meeting-response actions Outlook REST v2 exposes.
_RESPOND_ACTIONS = {
    'accept': 'accept',
    'decline': 'decline',
    'tentative': 'tentativelyaccept',
}


def cmd_respond(args, config, access_token, api_base):
    event_id, args = schema_mod.pop_positional_id(args)
    action = comment = ''
    notify = True
    while args:
        flag, args = args[0], args[1:]
        if flag == '--id':
            event_id, args = _require_value(flag, args)
        elif flag == '--action':
            action, args = _require_value(flag, args)
        elif flag == '--comment':
            comment, args = _require_value(flag, args)
        elif flag == '--no-notify':
            notify = False
        else:
            raise UsageError(f'Unknown flag: {flag}')

    if not event_id:
        raise UsageError('--id is required')
    if action not in _RESPOND_ACTIONS:
        raise UsageError('--action must be one of: accept, decline, tentative')

    debug = _debug_enabled(config)
    # Outlook REST action endpoints return 202 with an empty body, which
    # api_request decodes to {}. Gate on `is None` (the recoverable-error
    # signal), not falsiness, so an empty success body is not mistaken for
    # failure - same contract as cmd_delete.
    body = {'Comment': comment, 'SendResponse': notify}
    endpoint = f'{_event_path(event_id)}/{_RESPOND_ACTIONS[action]}'
    result = api_mod.api_request('POST', api_base, endpoint, access_token, body=body, debug=debug)
    if result is None:
        return 1
    print(json.dumps({'id': event_id, 'action': action, 'notified': notify}))
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
            raise UsageError(f'Unknown flag: {flag}')

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
    setup_auth - the dispatcher routes `config` here before auth.

    Webcal sources are managed through `owa-cal profiles add/delete`,
    not this command - they live in their own JSON store with secret
    handling, and conflating them with the flat KV config file made
    the data model harder to reason about.
    """
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
    return 0


def cmd_refresh(args, config):
    if args:
        raise UsageError(f'Unknown flag: {args[0]}')
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

AUTHED_COMMANDS = {'events', 'show', 'create', 'update', 'delete', 'respond', 'categories'}

# Commands the webcal/iCal source supports. The feed is read-only and
# carries no category metadata, so write commands, RSVP, and `categories`
# are rejected with a clear error before auth or HTTP is touched.
WEBCAL_READ_COMMANDS = {'events'}
WEBCAL_REJECTED_COMMANDS = {'create', 'update', 'delete', 'respond', 'categories'}

_EVENTS_FLAGS = [
    schema_mod.flag('--date', value='<date>', summary='Specific day (YYYY-MM-DD, today/tomorrow/yesterday, +n/-n, weekday[+n])'),
    schema_mod.flag('--from', value='<date>', summary='Start of range (same vocabulary as --date)'),
    schema_mod.flag('--to', value='<date>', summary='End of range (same vocabulary as --date)'),
    schema_mod.flag('--week', value='<n|rel>', summary='ISO week: number, current/last/next, or +n/-n'),
    schema_mod.flag('--month', value='<n|rel>', summary='Month: 1-12, current/last/next, or +n/-n (bare = current)'),
    schema_mod.flag('--year', value='<n|rel>', summary='Year: full year, current/last/next, or +n/-n'),
    schema_mod.flag('--search', value='<term>', summary='Search events by subject'),
    schema_mod.flag('--pretty', summary='Human-readable table (default: JSON)'),
    schema_mod.flag('--limit', value='<n>', summary='Max results per page (default 50, cap 200)'),
    schema_mod.flag('--all', summary='Follow @odata.nextLink until exhausted'),
]

_CREATE_FLAGS = [
    schema_mod.flag('--subject', value='<title>', summary='Event title', required=True),
    schema_mod.flag('--date', value='<date>', summary='Date (default: today)'),
    schema_mod.flag('--start', value='<HH:MM>', summary='Start time (default: 09:00)'),
    schema_mod.flag('--end', value='<HH:MM>', summary='End time (default: 10:00)'),
    schema_mod.flag('--category', value='<name>', summary='Category name', repeatable=True),
    schema_mod.flag('--attendee', value='<email>', summary='Required attendee', repeatable=True),
    schema_mod.flag('--optional-attendee', value='<email>', summary='Optional attendee', repeatable=True),
    schema_mod.flag('--reminder', value='<minutes>', summary='Reminder minutes before start'),
    schema_mod.flag('--recur', value='<daily|weekly>', summary='Recurrence pattern'),
    schema_mod.flag('--recur-interval', value='<n>', summary='Recurrence interval (default 1)'),
    schema_mod.flag('--recur-count', value='<n>', summary='Number of occurrences'),
    schema_mod.flag('--recur-until', value='<YYYY-MM-DD>', summary='Recur until date'),
    schema_mod.flag('--location', value='<place>', summary='Location'),
    schema_mod.flag('--body', value='<text>', summary='Description'),
    schema_mod.flag('--allday', summary='All-day event'),
    schema_mod.flag('--showas', value='<status>', summary='busy, free, tentative, oof'),
]

_SHOW_FLAGS = [
    schema_mod.flag('--id', value='<event-id>', summary='Event ID (flag or positional)', required=True),
]

_UPDATE_FLAGS = [
    schema_mod.flag('--id', value='<event-id>', summary='Event ID (flag or positional)', required=True),
    schema_mod.flag('--subject', value='<title>', summary='New event title'),
    schema_mod.flag('--date', value='<date>', summary='New date'),
    schema_mod.flag('--start', value='<HH:MM>', summary='New start time'),
    schema_mod.flag('--end', value='<HH:MM>', summary='New end time'),
    schema_mod.flag('--category', value='<name>', summary='Replace categories', repeatable=True),
    schema_mod.flag('--attendee', value='<email>', summary='Replace required attendees', repeatable=True),
    schema_mod.flag('--optional-attendee', value='<email>', summary='Replace optional attendees', repeatable=True),
    schema_mod.flag('--reminder', value='<minutes>', summary='Reminder minutes before start'),
    schema_mod.flag('--recur', value='<daily|weekly>', summary='Recurrence pattern'),
    schema_mod.flag('--recur-interval', value='<n>', summary='Recurrence interval (default 1)'),
    schema_mod.flag('--recur-count', value='<n>', summary='Number of occurrences'),
    schema_mod.flag('--recur-until', value='<YYYY-MM-DD>', summary='Recur until date'),
    schema_mod.flag('--location', value='<place>', summary='New location'),
    schema_mod.flag('--body', value='<text>', summary='New description'),
    schema_mod.flag('--showas', value='<status>', summary='busy, free, tentative, oof'),
]

_DELETE_FLAGS = [
    schema_mod.flag('--id', value='<event-id>', summary='Event ID (flag or positional)', required=True),
    schema_mod.flag('--confirm', summary='Skip confirmation prompt'),
]

_RESPOND_FLAGS = [
    schema_mod.flag('--id', value='<event-id>', summary='Event ID (flag or positional)', required=True),
    schema_mod.flag('--action', value='<accept|decline|tentative>', summary='Response to send', required=True),
    schema_mod.flag('--comment', value='<text>', summary='Optional note to the organizer'),
    schema_mod.flag('--no-notify', summary="Don't send a response back to the organizer"),
]

_CATEGORIES_FLAGS = [
    schema_mod.flag('--add', value='<name>', summary='Add a new master category'),
    schema_mod.flag('--pretty', summary='Human-readable table (default: JSON)'),
]

_PROFILES_FLAGS = [
    schema_mod.flag('list', summary='List all profiles (owa-cal + owa-piggy)'),
    schema_mod.flag('add <alias>', value='--webcal <url>', summary='Add a local webcal/iCal profile'),
    schema_mod.flag('delete <alias>', summary='Remove an owa-cal profile'),
    schema_mod.flag('--pretty', summary='Human-readable listing (default: JSON)'),
]

_CONFIG_FLAGS = [
    schema_mod.flag('--profile', value='<alias>', summary='Pin a default owa-piggy profile alias (owa_piggy_profile)'),
]

COMMAND_SCHEMA = [
    schema_mod.command('refresh', 'Force a token refresh', auth='outlook'),
    schema_mod.command('events', 'List calendar events', auth='outlook', flags=_EVENTS_FLAGS),
    schema_mod.command('show', 'Show full detail for a single event (attendees, organizer, body)', auth='outlook', flags=_SHOW_FLAGS),
    schema_mod.command('create', 'Create an event', auth='outlook', mutates=True, idempotent=False, flags=_CREATE_FLAGS),
    schema_mod.command('update', 'Update an event', auth='outlook', mutates=True, idempotent=True, flags=_UPDATE_FLAGS),
    schema_mod.command(
        'delete',
        'Delete an event',
        auth='outlook',
        mutates=True,
        destructive=True,
        confirmation=True,
        idempotent=False,
        flags=_DELETE_FLAGS,
    ),
    schema_mod.command(
        'respond',
        'Respond to a meeting invite (accept/decline/tentative)',
        auth='outlook',
        mutates=True,
        idempotent=False,
        flags=_RESPOND_FLAGS,
    ),
    schema_mod.command('categories', 'List or add master categories', auth='outlook', mutates=True, flags=_CATEGORIES_FLAGS),
    schema_mod.command('profiles', 'List/add/delete calendar profiles', mutates=True, flags=_PROFILES_FLAGS),
    schema_mod.command('config', 'View or update configuration', mutates=True, flags=_CONFIG_FLAGS),
]


def _resolve_source(config):
    """Resolve which calendar source this invocation should use.

    Returns one of:
        ('webcal', url)   - read from a webcal/iCal feed
        ('oauth', alias)  - use owa-piggy with the given profile alias
                            ('' meaning piggy's own default)

    Order ("closest profile wins"):
      1. A name set via --profile / config pin: if it matches a local
         webcal profile -> webcal. If it ALSO matches an owa-piggy
         profile, emit a stderr note - the user can run owa-piggy
         directly to escape the shadow.
      2. The named profile is not local -> forward to owa-piggy.
      3. No name set, but `OWA_CAL_WEBCAL_URL` env present -> webcal
         (ad-hoc, no name, useful for one-shot scripts).
      4. Otherwise -> oauth with no alias (piggy default).
    """
    name = (config.get('owa_piggy_profile') or '').strip()
    if name:
        local = profiles_mod.load_local().get(name)
        if isinstance(local, dict) and local.get('webcal_url'):
            piggy_set, _piggy_default = profiles_mod.piggy_aliases()
            if name in piggy_set:
                _info(
                    f"note: '{name}' is also an owa-piggy profile; "
                    f"using owa-cal's webcal source. Run "
                    f"`owa-piggy ... --profile {name}` directly to use "
                    f"the OAuth path."
                )
            return ('webcal', local['webcal_url'])
        return ('oauth', name)
    env_url = (os.environ.get('OWA_CAL_WEBCAL_URL') or '').strip()
    if env_url:
        return ('webcal', env_url)
    return ('oauth', '')


def _format_profiles_pretty(local_profiles, piggy_set, piggy_default):
    """Build the --pretty rendering of the merged profile listing.

    owa-cal entries first ("closest profile wins"), then owa-piggy.
    Shadow markers on both sides so the user can see the collision.
    URLs are never printed - they are bearer secrets.
    """
    lines = []
    if local_profiles:
        lines.append('owa-cal (webcal):')
        for alias in sorted(local_profiles):
            tag = (
                '  [also defined in owa-piggy; this wins]'
                if alias in piggy_set else ''
            )
            lines.append(f'  {alias}{tag}')
        lines.append('')
    if piggy_set:
        lines.append('owa-piggy (oauth):')
        for alias in sorted(piggy_set):
            markers = []
            if alias in local_profiles:
                markers.append('shadowed by owa-cal')
            if alias == piggy_default:
                markers.append('default')
            tag = f'  [{"; ".join(markers)}]' if markers else ''
            prefix = '* ' if alias == piggy_default else '  '
            lines.append(f'{prefix}{alias}{tag}')
    if not lines:
        return 'No profiles configured.'
    return '\n'.join(lines).rstrip()


def _profiles_json(local_profiles, piggy_set, piggy_default):
    """Build the JSON shape for `owa-cal profiles` (no --pretty).

    Flat list, owa-cal entries first, with shadow markers on each
    side. URLs are never included.
    """
    out = []
    for alias in sorted(local_profiles):
        out.append({
            'alias': alias,
            'source': 'owa-cal',
            'kind': 'webcal',
            'default': False,
            'shadows_owa_piggy': alias in piggy_set,
        })
    for alias in sorted(piggy_set):
        out.append({
            'alias': alias,
            'source': 'owa-piggy',
            'kind': 'oauth',
            'default': alias == piggy_default,
            'shadowed_by_owa_cal': alias in local_profiles,
        })
    return out


def cmd_profiles(args, config):
    """List, add, or delete calendar profiles.

    No auth - this command never reaches the network. The piggy
    listing is best-effort: if owa-piggy is unavailable we just show
    the local entries.
    """
    if not args or args[0].startswith('-'):
        return _profiles_list(args)
    sub, rest = args[0], args[1:]
    if sub == 'list':
        return _profiles_list(rest)
    if sub == 'add':
        return _profiles_add(rest)
    if sub == 'delete':
        return _profiles_delete(rest)
    _error(f'Unknown subcommand: {sub}. Try: profiles [list|add|delete]')
    return 1


def _profiles_list(args):
    pretty = False
    while args:
        flag, args = args[0], args[1:]
        if flag == '--pretty':
            pretty = True
        else:
            raise UsageError(f'Unknown flag: {flag}')
    local = profiles_mod.load_local()
    piggy_set, piggy_default = profiles_mod.piggy_aliases()
    if pretty:
        print(_format_profiles_pretty(local, piggy_set, piggy_default))
    else:
        print(json.dumps(_profiles_json(local, piggy_set, piggy_default)))
    return 0


def _profiles_add(args):
    alias = ''
    webcal = ''
    while args:
        flag, args = args[0], args[1:]
        if flag == '--webcal':
            webcal, args = _require_value(flag, args)
        elif flag.startswith('-'):
            raise UsageError(f'Unknown flag: {flag}')
        elif not alias:
            alias = flag
        else:
            raise UsageError(f'Unexpected argument: {flag}')
    if not alias:
        _error('profiles add requires an <alias>')
        return 1
    if not webcal:
        _error('profiles add requires --webcal <url>')
        return 1
    new = profiles_mod.add_local(alias, webcal)
    piggy_set, _default = profiles_mod.piggy_aliases()
    verb = 'created' if new else 'updated'
    _info(f"profile '{alias}' {verb} (webcal source)")
    if alias in piggy_set:
        _info(
            f"note: '{alias}' is also an owa-piggy profile. "
            f"`owa-cal --profile {alias}` will now use the webcal source; "
            f"run `owa-piggy ... --profile {alias}` directly for OAuth."
        )
    return 0


def _profiles_delete(args):
    alias = ''
    while args:
        flag, args = args[0], args[1:]
        if flag.startswith('-'):
            raise UsageError(f'Unknown flag: {flag}')
        elif not alias:
            alias = flag
        else:
            raise UsageError(f'Unexpected argument: {flag}')
    if not alias:
        _error('profiles delete requires an <alias>')
        return 1
    if profiles_mod.delete_local(alias):
        _info(f"profile '{alias}' removed")
        return 0
    # The alias might be a piggy profile - point the user at the right
    # tool rather than silently succeeding or failing.
    piggy_set, _default = profiles_mod.piggy_aliases()
    if alias in piggy_set:
        _error(
            f"'{alias}' is an owa-piggy profile, not an owa-cal profile. "
            f"Run `owa-piggy profiles delete {alias}` to remove it."
        )
        return 2
    _error(f"no owa-cal profile named '{alias}'")
    return 1


def _main(argv):
    handled = schema_mod.maybe_emit_schema(argv, tool='owa-cal', commands=COMMAND_SCHEMA)
    if handled is not None:
        return handled

    if not argv:
        print_help()
        return 0
    if argv[0] in ('help', '--help', '-h'):
        print_help()
        return 0
    if argv[0] in ('--version', '-v'):
        print(f'owa-cal {__version__}')
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
        cmd, rest, tool='owa-cal', commands=COMMAND_SCHEMA,
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
    if cmd == 'profiles':
        return cmd_profiles(rest, config)

    if cmd not in AUTHED_COMMANDS:
        raise UsageError(f"Unknown command: {cmd}. Run 'owa-cal help' for usage.")

    schema_mod.precheck_required_args(cmd, rest, commands=COMMAND_SCHEMA)

    # Source resolution short-circuits before auth: a named local
    # webcal profile, or OWA_CAL_WEBCAL_URL, takes the iCal path. Write
    # commands and `categories` are rejected against any webcal source
    # because the feed is read-only and carries no category metadata.
    source, value = _resolve_source(config)
    if source == 'webcal':
        if cmd in WEBCAL_REJECTED_COMMANDS:
            _error(
                f"'{cmd}' is not supported on a webcal source "
                f"(read-only feed). Use a different --profile or unset "
                f"OWA_CAL_WEBCAL_URL to use the Outlook REST path."
            )
            return 2
        if cmd in WEBCAL_READ_COMMANDS:
            config['webcal_url'] = value
            return cmd_events_webcal(rest, config)

    # source == 'oauth': fall through to setup_auth. The resolver may
    # have returned an explicit alias or '' (piggy default); we leave
    # `config['owa_piggy_profile']` untouched - existing auth code reads
    # it directly.
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
    if cmd == 'respond':
        return cmd_respond(rest, config, access_token, api_base)
    if cmd == 'categories':
        return cmd_categories(rest, config, access_token, api_base)

    # Unreachable: AUTHED_COMMANDS guarded above.
    return 1


# Delegated scopes that grant each calendar command (any-of), used by the
# --profile all fan-out to silently skip profiles with no calendar access at
# all (e.g. a DevOps-only profile that can't even mint an outlook token).
# Auth/local commands (refresh, config, profiles) are intentionally absent.
_CAL_SCOPES = frozenset({
    'Calendars.Read', 'Calendars.ReadWrite',
    'Calendars.Read.Shared', 'Calendars.ReadWrite.Shared',
})
COMMAND_SCOPES = {
    cmd: _CAL_SCOPES
    for cmd in ('events', 'create', 'update', 'delete', 'respond', 'categories')
}


def main(argv=None):
    return mode_mod.run_with_output_modes(
        'owa-cal', sys.argv[1:] if argv is None else argv, _main,
        interactive_commands=(),
        audience=auth_mod.AUDIENCE,
        command_scopes=COMMAND_SCOPES,
    )
