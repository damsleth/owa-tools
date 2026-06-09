"""Argument parsing and dispatch for the `owa-planner` command.

owa-planner is pipe-friendly: JSON on stdout, logs on stderr. --pretty
switches stdout to a human-readable view. It reads the Microsoft Graph
`/planner` surface on the `graph` audience - the OWA SPA token carries
Group.ReadWrite.All, which authorizes Planner reads even though it has no
Tasks.* scope. See auth.py.

Read-only v1. Writes are deferred (Planner PATCH needs the exact
`@odata.etag` in `If-Match`) - see AGENTS.md.

Subcommands are parsed manually (no argparse subparsers) to match the rest of
the suite; each cmd_* fn owns its own flag loop.
"""
import json
import os
import sys
import urllib.parse

from owa_core import modes as mode_mod
from owa_core import schema as schema_mod
from owa_core.errors import UsageError, emit_message

from . import __version__
from . import api as api_mod
from . import auth as auth_mod
from . import config as config_mod
from . import plans as plans_mod
from .format import (
    format_buckets_pretty,
    format_plans_pretty,
    format_task_pretty,
    format_tasks_pretty,
)


def _error(msg):
    emit_message(msg)


def _info(msg):
    print(msg, file=sys.stderr)


def _debug_enabled(config):
    return bool(config.get('debug')) or os.environ.get('PLANNER_DEBUG') == '1'


def _quote(value):
    return urllib.parse.quote(value, safe='')


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


def _require_value(flag, args):
    if not args:
        raise UsageError(f'{flag} requires a value')
    return args[0], args[1:]


def print_help():
    print("""owa-planner - Microsoft Planner CLI for Microsoft 365

Usage: owa-planner <command> [options]

Global options:
  --debug, --verbose  Print HTTP requests and response bodies on errors
                      (also: PLANNER_DEBUG=1)
  --profile <alias>   owa-piggy profile alias for this invocation.

Commands:
  plans               List Planner plans (mine, or --group <id>)
  buckets             List buckets in a plan (--plan <id>)
  tasks               List tasks (mine, or --plan <id>)
  task                Show one task with checklist + description
  config              View or update configuration
  refresh             Force a token refresh and verify auth
  help                Show this help

Plans options:
  --group <id>        List a group's plans instead of mine
  --pretty            Human-readable listing (default: JSON)
  --all               Follow @odata.nextLink until exhausted

Buckets options:
  --plan <id>         Plan id (or config default_plan)
  --pretty            Human-readable listing

Tasks options:
  --plan <id>         Limit to one plan (default: my assigned tasks)
  --bucket <id>       Filter to one bucket
  --status <status>   notstarted, inprogress, completed
  --pretty            Human-readable checklist
  --all               Follow @odata.nextLink until exhausted

Task options:
  --id <task-id>      Task id (flag or bare positional)
  --pretty            Human-readable detail

Config options:
  --profile <alias>   Pin a default owa-piggy profile alias
  --plan <id>         Pin a default plan id

Auth:
  owa-planner shells out to owa-piggy for a fresh access token on every call
  (audience: graph). Group.ReadWrite.All authorizes Planner reads; no Tasks.*
  scope is required.

Examples:
  owa-planner plans --pretty
  owa-planner buckets --plan <plan-id> --pretty
  owa-planner tasks --plan <plan-id> --status notstarted --pretty
  owa-planner tasks                       # my assigned tasks across plans
  owa-planner task <task-id> --pretty""")
    print()
    print(schema_mod.MULTI_PROFILE_HELP)
    print()
    print(schema_mod.MACHINE_SURFACE_HELP)


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

def _fetch(endpoint, all_pages, access_token, api_base, debug):
    if all_pages:
        items = api_mod.paginate_all(api_base, endpoint, access_token, debug=debug)
        if items is None:
            return None
        return {'value': items}
    return api_mod.api_get(api_base, endpoint, access_token, debug=debug)


def cmd_plans(args, config, access_token, api_base):
    group = ''
    pretty = all_pages = False
    while args:
        flag, args = args[0], args[1:]
        if flag == '--group':
            group, args = _require_value(flag, args)
        elif flag == '--pretty':
            pretty = True
        elif flag == '--all':
            all_pages = True
        else:
            raise UsageError(f'Unknown flag: {flag}')
    debug = _debug_enabled(config)
    endpoint = f'groups/{_quote(group)}/planner/plans' if group else 'me/planner/plans'
    data = _fetch(endpoint, all_pages, access_token, api_base, debug)
    if data is None:
        return 1
    rows = plans_mod.normalize_plans(data)
    print(format_plans_pretty(rows) if pretty else json.dumps(rows))
    return 0


def cmd_buckets(args, config, access_token, api_base):
    plan = ''
    pretty = all_pages = False
    while args:
        flag, args = args[0], args[1:]
        if flag == '--plan':
            plan, args = _require_value(flag, args)
        elif flag == '--pretty':
            pretty = True
        elif flag == '--all':
            all_pages = True
        else:
            raise UsageError(f'Unknown flag: {flag}')
    plan = plan or config.get('default_plan') or ''
    if not plan:
        raise UsageError('--plan is required (or set a default with: owa-planner config --plan <id>)')
    debug = _debug_enabled(config)
    endpoint = f'planner/plans/{_quote(plan)}/buckets'
    data = _fetch(endpoint, all_pages, access_token, api_base, debug)
    if data is None:
        return 1
    rows = plans_mod.normalize_buckets(data)
    print(format_buckets_pretty(rows) if pretty else json.dumps(rows))
    return 0


def cmd_tasks(args, config, access_token, api_base):
    plan = bucket = status = ''
    pretty = all_pages = False
    while args:
        flag, args = args[0], args[1:]
        if flag == '--plan':
            plan, args = _require_value(flag, args)
        elif flag == '--bucket':
            bucket, args = _require_value(flag, args)
        elif flag == '--status':
            status, args = _require_value(flag, args)
        elif flag == '--pretty':
            pretty = True
        elif flag == '--all':
            all_pages = True
        else:
            raise UsageError(f'Unknown flag: {flag}')
    debug = _debug_enabled(config)
    plan = plan or config.get('default_plan') or ''
    endpoint = f'planner/plans/{_quote(plan)}/tasks' if plan else 'me/planner/tasks'
    data = _fetch(endpoint, all_pages, access_token, api_base, debug)
    if data is None:
        return 1
    rows = plans_mod.normalize_tasks(data)
    want = plans_mod.normalize_status(status) if status else None
    if want:
        rows = [t for t in rows if t.get('status') == want]
    if bucket:
        rows = [t for t in rows if t.get('bucketId') == bucket]
    print(format_tasks_pretty(rows) if pretty else json.dumps(rows))
    return 0


def cmd_task(args, config, access_token, api_base):
    task_id, args = schema_mod.pop_positional_id(args)
    pretty = False
    while args:
        flag, args = args[0], args[1:]
        if flag == '--id':
            task_id, args = _require_value(flag, args)
        elif flag == '--pretty':
            pretty = True
        else:
            raise UsageError(f'Unknown flag: {flag}')
    if not task_id:
        raise UsageError('--id is required')
    debug = _debug_enabled(config)
    raw = api_mod.api_get(api_base, f'planner/tasks/{_quote(task_id)}', access_token, debug=debug)
    if raw is None:
        return 1
    task = plans_mod.normalize_task(raw)
    detail_raw = api_mod.api_get(
        api_base, f'planner/tasks/{_quote(task_id)}/details', access_token, debug=debug,
    )
    detail = plans_mod.normalize_task_detail(detail_raw) if detail_raw else {}
    task['detail'] = detail
    print(format_task_pretty(task, detail) if pretty else json.dumps(task))
    return 0


def cmd_config(args, config):
    profile = plan = ''
    while args:
        flag, args = args[0], args[1:]
        if flag == '--profile':
            profile, args = _require_value(flag, args)
        elif flag == '--plan':
            plan, args = _require_value(flag, args)
        else:
            raise UsageError(f'Unknown flag: {flag}')

    changed = False
    if profile:
        config_mod.config_set('owa_piggy_profile', profile)
        _info(f'default profile saved: {profile}')
        changed = True
    if plan:
        config_mod.config_set('default_plan', plan)
        _info(f'default plan saved: {plan}')
        changed = True
    if changed:
        return 0

    _info(f'Config file: {config_mod.CONFIG_PATH}')
    if config.get('owa_piggy_profile'):
        _info(f"  owa_piggy_profile={config.get('owa_piggy_profile')}")
    else:
        _info('  owa_piggy_profile=(not set - owa-piggy picks its default)')
    _info(f"  default_plan={config.get('default_plan') or '(not set)'}")
    return 0


def cmd_refresh(args, config):
    if args:
        raise UsageError(f'Unknown flag: {args[0]}')
    _info('Refreshing token...')
    access = auth_mod.do_token_refresh(config, debug=_debug_enabled(config))
    if not access:
        _error('Token refresh failed.')
        return 1
    me = api_mod.api_get(auth_mod.API_BASE, 'me', access, debug=_debug_enabled(config))
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

AUTHED_COMMANDS = {'plans', 'buckets', 'tasks', 'task'}

_PLANS_FLAGS = [
    schema_mod.flag('--group', value='<id>', summary="List a group's plans instead of mine"),
    schema_mod.flag('--pretty', summary='Human-readable listing (default: JSON)'),
    schema_mod.flag('--all', summary='Follow @odata.nextLink until exhausted'),
]

_BUCKETS_FLAGS = [
    schema_mod.flag('--plan', value='<id>', summary='Plan id (or config default_plan)'),
    schema_mod.flag('--pretty', summary='Human-readable listing (default: JSON)'),
    schema_mod.flag('--all', summary='Follow @odata.nextLink until exhausted'),
]

_TASKS_FLAGS = [
    schema_mod.flag('--plan', value='<id>', summary='Limit to one plan (default: my assigned tasks)'),
    schema_mod.flag('--bucket', value='<id>', summary='Filter to one bucket'),
    schema_mod.flag('--status', value='<status>', summary='notstarted, inprogress, completed'),
    schema_mod.flag('--pretty', summary='Human-readable checklist (default: JSON)'),
    schema_mod.flag('--all', summary='Follow @odata.nextLink until exhausted'),
]

_TASK_FLAGS = [
    schema_mod.flag('--id', value='<task-id>', summary='Task id (flag or positional)', required=True),
    schema_mod.flag('--pretty', summary='Human-readable detail (default: JSON)'),
]

_CONFIG_FLAGS = [
    schema_mod.flag('--profile', value='<alias>', summary='Pin a default owa-piggy profile alias'),
    schema_mod.flag('--plan', value='<id>', summary='Pin a default plan id'),
]

COMMAND_SCHEMA = [
    schema_mod.command('plans', 'List Planner plans', auth='graph', flags=_PLANS_FLAGS),
    schema_mod.command('buckets', 'List buckets in a plan', auth='graph', flags=_BUCKETS_FLAGS),
    schema_mod.command('tasks', 'List Planner tasks', auth='graph', flags=_TASKS_FLAGS),
    schema_mod.command('task', 'Show one task with details', auth='graph', flags=_TASK_FLAGS),
    schema_mod.command('refresh', 'Force a token refresh', auth='graph'),
    schema_mod.command('config', 'View or update configuration', mutates=True, flags=_CONFIG_FLAGS),
]


def _main(argv):
    handled = schema_mod.maybe_emit_schema(argv, tool='owa-planner', commands=COMMAND_SCHEMA)
    if handled is not None:
        return handled

    if not argv:
        print_help()
        return 0
    if argv[0] in ('help', '--help', '-h'):
        print_help()
        return 0
    if argv[0] in ('--version', '-v'):
        print(f'owa-planner {__version__}')
        return 0

    debug_flag = False
    profile_override = ''
    # Strip global flags (--debug/--verbose, --profile) from anywhere in argv.
    # Exception: on `owa-planner config`, --profile is a subcommand flag.
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
        cmd, rest, tool='owa-planner', commands=COMMAND_SCHEMA,
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
        raise UsageError(f"Unknown command: {cmd}. Run 'owa-planner help' for usage.")

    schema_mod.precheck_required_args(cmd, rest, commands=COMMAND_SCHEMA)

    access_token, api_base = auth_mod.setup_auth(config, debug=_debug_enabled(config))

    if cmd == 'plans':
        return cmd_plans(rest, config, access_token, api_base)
    if cmd == 'buckets':
        return cmd_buckets(rest, config, access_token, api_base)
    if cmd == 'tasks':
        return cmd_tasks(rest, config, access_token, api_base)
    if cmd == 'task':
        return cmd_task(rest, config, access_token, api_base)

    # Unreachable: AUTHED_COMMANDS guarded above.
    return 1


def main(argv=None):
    return mode_mod.run_with_output_modes(
        'owa-planner', sys.argv[1:] if argv is None else argv, _main,
    )
