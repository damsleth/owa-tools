"""Argument parsing and dispatch for the `owa-todo` command.

owa-todo is pipe-friendly: JSON on stdout, logs on stderr. --pretty
switches stdout to a human-readable checklist. It talks to the Outlook
REST v2.0 Tasks API (`me/taskfolders`, `me/tasks`) on the `outlook`
audience - the same token owa-cal/owa-mail use, which (on a To Do-capable
profile) already carries Tasks.ReadWrite. See auth.py.

Subcommands are parsed manually (no argparse subparsers) to match the
rest of the suite; each cmd_* fn owns its own flag loop.
"""
import json
import os
import sys
import urllib.parse
from datetime import date, timedelta

from owa_core import modes as mode_mod
from owa_core import schema as schema_mod
from owa_core import tty as tty_mod
from owa_core.errors import UsageError, _require_value, emit_error, emit_message

from . import __version__
from . import api as api_mod
from . import auth as auth_mod
from . import config as config_mod
from . import tasks as tasks_mod
from .format import format_folders_pretty, format_tasks_pretty


def _error(msg):
    emit_message(msg)


def _info(msg):
    print(msg, file=sys.stderr)


def _debug_enabled(config):
    return bool(config.get('debug')) or os.environ.get('TODO_DEBUG') == '1'


def _task_path(task_id):
    return f'me/tasks/{urllib.parse.quote(task_id, safe="")}'


def _folder_tasks_path(folder_id):
    return f'me/taskfolders/{urllib.parse.quote(folder_id, safe="")}/tasks'


def _folder_path(folder_id):
    return f'me/taskfolders/{urllib.parse.quote(folder_id, safe="")}'


def _resolve_date(value):
    if value == 'today':
        return date.today().strftime('%Y-%m-%d')
    if value == 'tomorrow':
        return (date.today() + timedelta(days=1)).strftime('%Y-%m-%d')
    if value == 'yesterday':
        return (date.today() - timedelta(days=1)).strftime('%Y-%m-%d')
    return value


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


def _require_int(flag, args):
    v, args = _require_value(flag, args)
    try:
        return int(v), args
    except ValueError:
        raise UsageError(f'{flag} requires an integer, got: {v}')


def print_help():
    print("""owa-todo - Microsoft To Do task CLI for Outlook / Microsoft 365

Usage: owa-todo <command> [options]

Global options:
  --debug, --verbose  Print HTTP requests and response bodies on errors
                      (also: TODO_DEBUG=1)
  --profile <alias>   owa-piggy profile alias for this invocation.
                      Overrides owa_piggy_profile in the config file.

Commands:
  lists               List task folders (To Do lists)
  list-create         Create a To Do list
  list-rename         Rename a To Do list
  list-delete         Delete a To Do list
  tasks               List tasks (default: across all folders)
  create              Create a task
  update              Update a task
  done                Mark a task completed
  undone              Mark a task not started (reopen)
  delete              Delete a task
  config              View or update configuration
  refresh             Force a token refresh and verify auth
  help                Show this help

Tasks options:
  --folder <id|name>  Limit to one folder (default: all, or config default_folder)
  --status <status>   Filter: notstarted, inprogress, completed, waiting, deferred
  --search <term>     Filter tasks by subject
  --filter <odata>    Server-side $filter passthrough
  --orderby <odata>   Server-side $orderby passthrough
  --pretty            Human-readable checklist (default: JSON)
  --limit <n>         Max results per page (default 50, cap 200)
  --all               Follow @odata.nextLink until exhausted

Create options:
  --subject <title>   Task title (required)
  --folder <id|name>  Target folder (default: the default Tasks list)
  --due <date>        Due date (YYYY-MM-DD, today, tomorrow)
  --start <date>      Start date
  --reminder <iso>    Reminder datetime (YYYY-MM-DDTHH:MM)
  --recurrence <r>    Recurrence: daily or weekly
  --category <name>   Category (repeatable)
  --importance <level>  low|normal|high
  --body <text>       Notes

Update options:
  --id <task-id>      Task ID (required)
  --subject, --due, --start, --reminder, --recurrence, --category,
  --status, --importance, --body

Done / Undone options:
  --id <task-id>      Task ID (required)

List options:
  list-create --name <name>
  list-rename --id <id|name> --name <name>
  list-delete --id <id|name> [--confirm]

Delete options:
  --id <task-id>      Task ID (required)
  --confirm           Skip confirmation prompt

Config options:
  --profile <alias>   Pin a default owa-piggy profile alias
  --folder <id>       Pin a default task folder

Auth:
  owa-todo shells out to owa-piggy for a fresh access token on every
  call (audience: outlook). Tasks.ReadWrite must be granted on the
  active profile; strict Conditional Access policies can withhold it,
  in which case calls exit 12 (access denied).

Tasks carry opaque ids: address one via --id or as a bare positional
argument (`owa-todo done <id>` == `owa-todo done --id <id>`).

Examples:
  owa-todo lists --pretty
  owa-todo tasks --pretty
  owa-todo tasks --folder "Groceries" --status notstarted --pretty
  owa-todo create --subject "Buy milk" --due tomorrow --importance high
  owa-todo update --id AAMk... --due 2026-06-01
  owa-todo create --subject "Standup" --recurrence daily --reminder 2026-06-01T09:00
  owa-todo create --subject "Pay rent" --category bills --category home
  owa-todo done --id AAMk...
  owa-todo undone --id AAMk...
  owa-todo list-create --name "Groceries"
  owa-todo delete --id AAMk...""")
    print()
    print(schema_mod.MULTI_PROFILE_HELP)
    print()
    print(schema_mod.MACHINE_SURFACE_HELP)


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

def _resolve_folder(value, access_token, api_base, debug):
    """Resolve a --folder value (folder name or Id) to a folder Id.

    Returns (folder_id, None) on success, or (None, rc) on failure so
    callers can `return rc`.
    """
    data = api_mod.api_get(api_base, 'me/taskfolders', access_token, debug=debug)
    if data is None:
        return None, 1
    folders = tasks_mod.normalize_folders(data)
    low = value.lower()
    for f in folders:
        if (f.get('name') or '').lower() == low:
            return f['id'], None
    for f in folders:
        if f.get('id') == value:
            return f['id'], None
    _error(f"no task folder named or with id '{value}'")
    return None, 2


def _fetch_tasks(endpoint, all_pages, access_token, api_base, debug):
    if all_pages:
        items = api_mod.paginate_all(api_base, endpoint, access_token, debug=debug)
        if items is None:
            return None
        return {'value': items}
    data = api_mod.api_get(api_base, endpoint, access_token, debug=debug)
    return data


def cmd_lists(args, config, access_token, api_base):
    pretty = False
    all_pages = False
    while args:
        flag, args = args[0], args[1:]
        if flag == '--pretty':
            pretty = True
        elif flag == '--all':
            all_pages = True
        else:
            raise UsageError(f'Unknown flag: {flag}')
    debug = _debug_enabled(config)
    data = _fetch_tasks('me/taskfolders', all_pages, access_token, api_base, debug)
    if data is None:
        return 1
    folders = tasks_mod.normalize_folders(data)
    if pretty:
        print(format_folders_pretty(folders))
    else:
        print(json.dumps(folders))
    return 0


def cmd_list_create(args, config, access_token, api_base):
    name = ''
    while args:
        flag, args = args[0], args[1:]
        if flag == '--name':
            name, args = _require_value(flag, args)
        else:
            raise UsageError(f'Unknown flag: {flag}')
    if not name:
        raise UsageError('--name is required')
    debug = _debug_enabled(config)
    result = api_mod.api_request(
        'POST', api_base, 'me/taskfolders', access_token,
        body=tasks_mod.build_folder_json(name), debug=debug,
    )
    if not result:
        return 1
    print(json.dumps(tasks_mod.normalize_folder(result)))
    return 0


def cmd_list_rename(args, config, access_token, api_base):
    folder = name = ''
    folder, args = schema_mod.pop_positional_id(args)
    while args:
        flag, args = args[0], args[1:]
        if flag == '--id':
            folder, args = _require_value(flag, args)
        elif flag == '--name':
            name, args = _require_value(flag, args)
        else:
            raise UsageError(f'Unknown flag: {flag}')
    if not folder:
        raise UsageError('--id is required')
    if not name:
        raise UsageError('--name is required')
    debug = _debug_enabled(config)
    folder_id, rc = _resolve_folder(folder, access_token, api_base, debug)
    if folder_id is None:
        return rc
    result = api_mod.api_request(
        'PATCH', api_base, _folder_path(folder_id), access_token,
        body=tasks_mod.build_folder_json(name), debug=debug,
    )
    if not result:
        return 1
    print(json.dumps(tasks_mod.normalize_folder(result)))
    return 0


def cmd_list_delete(args, config, access_token, api_base):
    folder = ''
    confirm = False
    folder, args = schema_mod.pop_positional_id(args)
    while args:
        flag, args = args[0], args[1:]
        if flag == '--id':
            folder, args = _require_value(flag, args)
        elif flag == '--confirm':
            confirm = True
        else:
            raise UsageError(f'Unknown flag: {flag}')
    if not folder:
        raise UsageError('--id is required')

    debug = _debug_enabled(config)
    folder_id, rc = _resolve_folder(folder, access_token, api_base, debug)
    if folder_id is None:
        return rc
    if not confirm:
        try:
            tty_mod.require_confirm_or_tty(action='delete list')
        except UsageError as error:
            return emit_error(error)
        if not tty_mod.confirm(
            f"\033[33mDelete list '{folder}'? (y/N): \033[0m"
        ):
            _info('Aborted.')
            return 0

    result = api_mod.api_request('DELETE', api_base, _folder_path(folder_id), access_token, debug=debug)
    if result is None:
        return 1
    _info('Deleted.')
    return 0


def cmd_tasks(args, config, access_token, api_base):
    folder = status = search = filter_q = orderby = ''
    pretty = all_pages = False
    limit = 50
    while args:
        flag, args = args[0], args[1:]
        if flag == '--folder':
            folder, args = _require_value(flag, args)
        elif flag == '--status':
            status, args = _require_value(flag, args)
        elif flag == '--search':
            search, args = _require_value(flag, args)
        elif flag == '--filter':
            filter_q, args = _require_value(flag, args)
        elif flag == '--orderby':
            orderby, args = _require_value(flag, args)
        elif flag == '--pretty':
            pretty = True
        elif flag == '--all':
            all_pages = True
        elif flag == '--limit':
            limit, args = _require_int(flag, args)
            limit = max(1, min(limit, 200))
        else:
            raise UsageError(f'Unknown flag: {flag}')

    debug = _debug_enabled(config)
    folder = folder or config.get('default_folder') or ''
    if folder:
        folder_id, rc = _resolve_folder(folder, access_token, api_base, debug)
        if folder_id is None:
            return rc
        base_endpoint = _folder_tasks_path(folder_id)
    else:
        base_endpoint = 'me/tasks'

    params = {'$top': limit}
    if filter_q:
        params['$filter'] = filter_q
    if orderby:
        params['$orderby'] = orderby
    endpoint = f'{base_endpoint}?{api_mod.build_query(params)}'
    data = _fetch_tasks(endpoint, all_pages, access_token, api_base, debug)
    if data is None:
        return 1

    normalized = tasks_mod.normalize_tasks(data)
    want_status = tasks_mod.normalize_status(status) if status else None
    if want_status:
        normalized = [t for t in normalized if t.get('status') == want_status]
    if search:
        needle = search.lower()
        normalized = [t for t in normalized if needle in (t.get('subject') or '').lower()]
    if pretty:
        print(format_tasks_pretty(normalized))
    else:
        print(json.dumps(normalized))
    return 0


def _resolve_create_folder(folder, config, access_token, api_base, debug):
    """Pick the POST endpoint for create: a named/default folder's tasks
    collection, or the default `me/tasks`. Returns (endpoint, None) or
    (None, rc)."""
    folder = folder or config.get('default_folder') or ''
    if not folder:
        return 'me/tasks', None
    folder_id, rc = _resolve_folder(folder, access_token, api_base, debug)
    if folder_id is None:
        return None, rc
    return _folder_tasks_path(folder_id), None


def _resolve_recurrence(value):
    pattern = tasks_mod.normalize_recurrence(value)
    if pattern is None:
        raise UsageError(f'--recurrence must be one of: daily, weekly (got: {value})')
    return pattern


def cmd_create(args, config, access_token, api_base):
    subject = folder = due = start = importance = body_text = reminder = ''
    recurrence = None
    categories = []
    while args:
        flag, args = args[0], args[1:]
        if flag == '--subject':
            subject, args = _require_value(flag, args)
        elif flag == '--folder':
            folder, args = _require_value(flag, args)
        elif flag == '--due':
            v, args = _require_value(flag, args); due = _resolve_date(v)
        elif flag == '--start':
            v, args = _require_value(flag, args); start = _resolve_date(v)
        elif flag == '--importance':
            importance, args = _require_value(flag, args)
        elif flag == '--body':
            body_text, args = _require_value(flag, args)
        elif flag == '--reminder':
            reminder, args = _require_value(flag, args)
        elif flag == '--recurrence':
            v, args = _require_value(flag, args); recurrence = _resolve_recurrence(v)
        elif flag == '--category':
            v, args = _require_value(flag, args); categories.append(v)
        else:
            raise UsageError(f'Unknown flag: {flag}')

    if not subject:
        raise UsageError('--subject is required')

    debug = _debug_enabled(config)
    tz = config.get('default_timezone') or config_mod.DEFAULT_TIMEZONE
    body = tasks_mod.build_task_json(
        subject, importance=importance, due=due, start=start,
        body_text=body_text, tz=tz, reminder=reminder,
        recurrence=recurrence, categories=categories,
    )
    endpoint, rc = _resolve_create_folder(folder, config, access_token, api_base, debug)
    if endpoint is None:
        return rc
    result = api_mod.api_request('POST', api_base, endpoint, access_token, body=body, debug=debug)
    if not result:
        return 1
    print(json.dumps(tasks_mod.normalize_task(result)))
    return 0


def cmd_update(args, config, access_token, api_base):
    task_id, args = schema_mod.pop_positional_id(args)
    fields = {}
    while args:
        flag, args = args[0], args[1:]
        if flag == '--id':
            task_id, args = _require_value(flag, args)
        elif flag == '--subject':
            fields['subject'], args = _require_value(flag, args)
        elif flag == '--importance':
            fields['importance'], args = _require_value(flag, args)
        elif flag == '--status':
            fields['status'], args = _require_value(flag, args)
        elif flag == '--body':
            fields['body'], args = _require_value(flag, args)
        elif flag == '--due':
            v, args = _require_value(flag, args); fields['due'] = _resolve_date(v)
        elif flag == '--start':
            v, args = _require_value(flag, args); fields['start'] = _resolve_date(v)
        elif flag == '--reminder':
            fields['reminder'], args = _require_value(flag, args)
        elif flag == '--recurrence':
            v, args = _require_value(flag, args); fields['recurrence'] = _resolve_recurrence(v)
        elif flag == '--category':
            v, args = _require_value(flag, args)
            fields.setdefault('categories', []).append(v)
        else:
            raise UsageError(f'Unknown flag: {flag}')

    if not task_id:
        raise UsageError('--id is required')
    if not fields:
        _error(
            'update requires at least one field '
            '(--subject, --status, --importance, --due, --start, --body, '
            '--reminder, --recurrence, --category)'
        )
        return 1

    debug = _debug_enabled(config)
    tz = config.get('default_timezone') or config_mod.DEFAULT_TIMEZONE
    patch = tasks_mod.build_task_patch(fields, tz)
    result = api_mod.api_request('PATCH', api_base, _task_path(task_id), access_token, body=patch, debug=debug)
    if not result:
        return 1
    print(json.dumps(tasks_mod.normalize_task(result)))
    return 0


def cmd_done(args, config, access_token, api_base):
    task_id, args = schema_mod.pop_positional_id(args)
    while args:
        flag, args = args[0], args[1:]
        if flag == '--id':
            task_id, args = _require_value(flag, args)
        else:
            raise UsageError(f'Unknown flag: {flag}')
    if not task_id:
        raise UsageError('--id is required')
    debug = _debug_enabled(config)
    result = api_mod.api_request(
        'PATCH', api_base, _task_path(task_id), access_token,
        body={'Status': 'Completed'}, debug=debug,
    )
    if not result:
        return 1
    print(json.dumps(tasks_mod.normalize_task(result)))
    return 0


def cmd_undone(args, config, access_token, api_base):
    task_id, args = schema_mod.pop_positional_id(args)
    while args:
        flag, args = args[0], args[1:]
        if flag == '--id':
            task_id, args = _require_value(flag, args)
        else:
            raise UsageError(f'Unknown flag: {flag}')
    if not task_id:
        raise UsageError('--id is required')
    debug = _debug_enabled(config)
    result = api_mod.api_request(
        'PATCH', api_base, _task_path(task_id), access_token,
        body={'Status': 'NotStarted'}, debug=debug,
    )
    if not result:
        return 1
    print(json.dumps(tasks_mod.normalize_task(result)))
    return 0


def cmd_delete(args, config, access_token, api_base):
    task_id, args = schema_mod.pop_positional_id(args)
    confirm = False
    while args:
        flag, args = args[0], args[1:]
        if flag == '--id':
            task_id, args = _require_value(flag, args)
        elif flag == '--confirm':
            confirm = True
        else:
            raise UsageError(f'Unknown flag: {flag}')
    if not task_id:
        raise UsageError('--id is required')

    debug = _debug_enabled(config)
    if not confirm:
        try:
            tty_mod.require_confirm_or_tty(action='delete task')
        except UsageError as error:
            return emit_error(error)
        existing = api_mod.api_get(api_base, _task_path(task_id), access_token, debug=debug)
        if not existing:
            return 1
        task = tasks_mod.normalize_task(existing)
        if not tty_mod.confirm(
            f"\033[33mDelete '{task.get('subject','')}'? (y/N): \033[0m"
        ):
            _info('Aborted.')
            return 0

    result = api_mod.api_request('DELETE', api_base, _task_path(task_id), access_token, debug=debug)
    if result is None:
        return 1
    _info('Deleted.')
    return 0


def cmd_config(args, config):
    profile = folder = ''
    while args:
        flag, args = args[0], args[1:]
        if flag == '--profile':
            profile, args = _require_value(flag, args)
        elif flag == '--folder':
            folder, args = _require_value(flag, args)
        else:
            raise UsageError(f'Unknown flag: {flag}')

    changed = False
    if profile:
        config_mod.config_set('owa_piggy_profile', profile)
        _info(f'default profile saved: {profile}')
        changed = True
    if folder:
        config_mod.config_set('default_folder', folder)
        _info(f'default folder saved: {folder}')
        changed = True
    if changed:
        return 0

    _info(f'Config file: {config_mod.CONFIG_PATH}')
    if config.get('owa_piggy_profile'):
        _info(f"  owa_piggy_profile={config.get('owa_piggy_profile')}")
    else:
        _info('  owa_piggy_profile=(not set - owa-piggy picks its default)')
    _info(f"  default_folder={config.get('default_folder') or '(not set - default Tasks list)'}")
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

AUTHED_COMMANDS = {
    'lists', 'list-create', 'list-rename', 'list-delete',
    'tasks', 'create', 'update', 'done', 'undone', 'delete',
}

_LISTS_FLAGS = [
    schema_mod.flag('--pretty', summary='Human-readable listing (default: JSON)'),
    schema_mod.flag('--all', summary='Follow @odata.nextLink until exhausted'),
]

_TASKS_FLAGS = [
    schema_mod.flag('--folder', value='<id|name>', summary='Limit to one folder'),
    schema_mod.flag('--status', value='<status>', summary='notstarted, inprogress, completed, waiting, deferred'),
    schema_mod.flag('--search', value='<term>', summary='Filter tasks by subject'),
    schema_mod.flag('--filter', value='<odata>', summary='Server-side $filter passthrough'),
    schema_mod.flag('--orderby', value='<odata>', summary='Server-side $orderby passthrough'),
    schema_mod.flag('--pretty', summary='Human-readable checklist (default: JSON)'),
    schema_mod.flag('--limit', value='<n>', summary='Max results per page (default 50, cap 200)'),
    schema_mod.flag('--all', summary='Follow @odata.nextLink until exhausted'),
]

_CREATE_FLAGS = [
    schema_mod.flag('--subject', value='<title>', summary='Task title', required=True),
    schema_mod.flag('--folder', value='<id|name>', summary='Target folder (default: default Tasks list)'),
    schema_mod.flag('--due', value='<date>', summary='Due date (YYYY-MM-DD, today, tomorrow)'),
    schema_mod.flag('--start', value='<date>', summary='Start date'),
    schema_mod.flag('--reminder', value='<iso>', summary='Reminder datetime (YYYY-MM-DDTHH:MM)'),
    schema_mod.flag('--recurrence', value='<daily|weekly>', summary='Recurrence cadence'),
    schema_mod.flag('--category', value='<name>', summary='Category (repeatable)', repeatable=True),
    schema_mod.flag('--importance', value='<level>', summary='low|normal|high'),
    schema_mod.flag('--body', value='<text>', summary='Notes'),
]

_UPDATE_FLAGS = [
    schema_mod.flag('--id', value='<task-id>', summary='Task ID (flag or positional)', required=True),
    schema_mod.flag('--subject', value='<title>', summary='New title'),
    schema_mod.flag('--due', value='<date>', summary='New due date'),
    schema_mod.flag('--start', value='<date>', summary='New start date'),
    schema_mod.flag('--reminder', value='<iso>', summary='Reminder datetime (YYYY-MM-DDTHH:MM)'),
    schema_mod.flag('--recurrence', value='<daily|weekly>', summary='Recurrence cadence'),
    schema_mod.flag('--category', value='<name>', summary='Category (repeatable)', repeatable=True),
    schema_mod.flag('--status', value='<status>', summary='notstarted, inprogress, completed, waiting, deferred'),
    schema_mod.flag('--importance', value='<level>', summary='low|normal|high'),
    schema_mod.flag('--body', value='<text>', summary='New notes'),
]

_DONE_FLAGS = [
    schema_mod.flag('--id', value='<task-id>', summary='Task ID (flag or positional)', required=True),
]

_UNDONE_FLAGS = [
    schema_mod.flag('--id', value='<task-id>', summary='Task ID (flag or positional)', required=True),
]

_LIST_CREATE_FLAGS = [
    schema_mod.flag('--name', value='<name>', summary='New list name', required=True),
]

_LIST_RENAME_FLAGS = [
    schema_mod.flag('--id', value='<id|name>', summary='List ID or name (flag or positional)', required=True),
    schema_mod.flag('--name', value='<name>', summary='New list name', required=True),
]

_LIST_DELETE_FLAGS = [
    schema_mod.flag('--id', value='<id|name>', summary='List ID or name (flag or positional)', required=True),
    schema_mod.flag('--confirm', summary='Skip confirmation prompt'),
]

_DELETE_FLAGS = [
    schema_mod.flag('--id', value='<task-id>', summary='Task ID (flag or positional)', required=True),
    schema_mod.flag('--confirm', summary='Skip confirmation prompt'),
]

_CONFIG_FLAGS = [
    schema_mod.flag('--profile', value='<alias>', summary='Pin a default owa-piggy profile alias (owa_piggy_profile)'),
    schema_mod.flag('--folder', value='<id>', summary='Pin a default task folder'),
]

COMMAND_SCHEMA = [
    schema_mod.command('lists', 'List task folders (To Do lists)', auth='outlook', flags=_LISTS_FLAGS),
    schema_mod.command('list-create', 'Create a To Do list', auth='outlook', mutates=True, idempotent=False, flags=_LIST_CREATE_FLAGS),
    schema_mod.command('list-rename', 'Rename a To Do list', auth='outlook', mutates=True, idempotent=True, flags=_LIST_RENAME_FLAGS),
    schema_mod.command(
        'list-delete',
        'Delete a To Do list',
        auth='outlook',
        mutates=True,
        destructive=True,
        confirmation=True,
        idempotent=False,
        flags=_LIST_DELETE_FLAGS,
    ),
    schema_mod.command('tasks', 'List tasks', auth='outlook', flags=_TASKS_FLAGS),
    schema_mod.command('create', 'Create a task', auth='outlook', mutates=True, idempotent=False, flags=_CREATE_FLAGS),
    schema_mod.command('update', 'Update a task', auth='outlook', mutates=True, idempotent=True, flags=_UPDATE_FLAGS),
    schema_mod.command('done', 'Mark a task completed', auth='outlook', mutates=True, idempotent=True, flags=_DONE_FLAGS),
    schema_mod.command('undone', 'Mark a task not started (reopen)', auth='outlook', mutates=True, idempotent=True, flags=_UNDONE_FLAGS),
    schema_mod.command(
        'delete',
        'Delete a task',
        auth='outlook',
        mutates=True,
        destructive=True,
        confirmation=True,
        idempotent=False,
        flags=_DELETE_FLAGS,
    ),
    schema_mod.command('refresh', 'Force a token refresh', auth='outlook'),
    schema_mod.command('config', 'View or update configuration', mutates=True, flags=_CONFIG_FLAGS),
]


def _main(argv):
    handled = schema_mod.maybe_emit_schema(argv, tool='owa-todo', commands=COMMAND_SCHEMA)
    if handled is not None:
        return handled

    if not argv:
        print_help()
        return 0
    if argv[0] in ('help', '--help', '-h'):
        print_help()
        return 0
    if argv[0] in ('--version', '-v'):
        print(f'owa-todo {__version__}')
        return 0

    debug_flag = False
    profile_override = ''
    # Strip global flags (--debug/--verbose, --profile) from anywhere in
    # argv. Exception: on `owa-todo config`, --profile is a subcommand flag.
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
        cmd, rest, tool='owa-todo', commands=COMMAND_SCHEMA,
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
        raise UsageError(f"Unknown command: {cmd}. Run 'owa-todo help' for usage.")

    schema_mod.precheck_required_args(cmd, rest, commands=COMMAND_SCHEMA)

    access_token, api_base = auth_mod.setup_auth(config, debug=_debug_enabled(config))

    if cmd == 'lists':
        return cmd_lists(rest, config, access_token, api_base)
    if cmd == 'list-create':
        return cmd_list_create(rest, config, access_token, api_base)
    if cmd == 'list-rename':
        return cmd_list_rename(rest, config, access_token, api_base)
    if cmd == 'list-delete':
        return cmd_list_delete(rest, config, access_token, api_base)
    if cmd == 'tasks':
        return cmd_tasks(rest, config, access_token, api_base)
    if cmd == 'create':
        return cmd_create(rest, config, access_token, api_base)
    if cmd == 'update':
        return cmd_update(rest, config, access_token, api_base)
    if cmd == 'done':
        return cmd_done(rest, config, access_token, api_base)
    if cmd == 'undone':
        return cmd_undone(rest, config, access_token, api_base)
    if cmd == 'delete':
        return cmd_delete(rest, config, access_token, api_base)

    # Unreachable: AUTHED_COMMANDS guarded above.
    return 1


def main(argv=None):
    return mode_mod.run_with_output_modes(
        'owa-todo', sys.argv[1:] if argv is None else argv, _main,
    )
