"""Argument parsing and dispatch for the `owa-teams` command.

owa-teams is pipe-friendly: JSON on stdout, logs on stderr. --pretty switches
stdout to a human-readable view. It reads Microsoft Teams across two doors
(see auth.py): Graph for enumeration (teams / channels / chats) and the
regional chat service for message bodies (channel + chat messages), which the
plain Graph token cannot read under owa-piggy's FOCI client.

Read-only v1. Posting messages, listing team members, and Teams meeting
metadata (which belongs with owa-cal) are deferred - see AGENTS.md.

Subcommands are parsed manually (no argparse subparsers) to match the rest of
the suite; each cmd_* fn owns its own flag loop and acquires the audience it
needs.
"""
import json
import os
import sys

from owa_core import modes as mode_mod
from owa_core import schema as schema_mod
from owa_core.errors import OwaError, UsageError, emit_error, emit_message

from . import __version__
from . import api as api_mod
from . import auth as auth_mod
from . import config as config_mod
from . import teams as teams_mod
from .format import (
    format_channels_pretty,
    format_chats_pretty,
    format_messages_pretty,
    format_teams_pretty,
)


def _error(msg):
    emit_message(msg)


def _info(msg):
    print(msg, file=sys.stderr)


def _debug_enabled(config):
    return bool(config.get('debug')) or os.environ.get('TEAMS_DEBUG') == '1'


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


def _require_int(flag, args):
    value, args = _require_value(flag, args)
    try:
        return int(value), args
    except ValueError:
        raise UsageError(f'{flag} requires an integer, got: {value}')


def _page_size(config, default=50):
    try:
        return max(1, min(int(config.get('page_size') or default), 50))
    except (TypeError, ValueError):
        return default


def print_help():
    print("""owa-teams - Microsoft Teams CLI for Microsoft 365

Usage: owa-teams <command> [options]

Global options:
  --debug, --verbose  Print HTTP requests and response bodies on errors
                      (also: TEAMS_DEBUG=1)
  --profile <alias>   owa-piggy profile alias for this invocation.

Commands:
  teams               List my joined teams (alias: ls)
  channels            List a team's channels (--team <id>)
  chats               List my 1:1 / group / meeting chats
  messages            Read channel or chat messages (--channel <id> | --chat <id>)
  config              View or update configuration
  refresh             Force a token refresh and verify Graph access
  help                Show this help

Channels:
  channels --team <team-id>      Team id (flag or bare positional)

Messages:
  messages --channel <id>        Channel conversation id (19:...@thread.tacv2);
                                 posts + replies, threaded by rootMessageId.
  messages --chat <id>           Chat conversation id (19:...@unq.gbl.spaces);
                                 flat message list.
  --team <id>                    Team id, echoed into channel-message metadata.
  --since <iso>                  Only messages at/after this ISO-8601 time; stops
                                 paging older once the cutoff is crossed.
  --limit <n>                    Max pages to fetch (default 4, ~50 msgs/page).
  --all                          Include system events and empty bodies.

Auth:
  Enumeration (teams/channels/chats) uses the Graph token. Message bodies use
  an ic3-audience token against the regional chat service. The region defaults
  to 'emea'; pin another with: owa-teams config --region <emea|amer|apac|...>

Examples:
  owa-teams teams --pretty
  owa-teams channels --team 3360397c-8ad3-499e-8d71-a83856c0f252 --pretty
  owa-teams chats --type meeting
  owa-teams messages --channel "19:abc@thread.tacv2" --pretty
  owa-teams messages --chat "19:def@unq.gbl.spaces" --limit 2""")
    print()
    print(schema_mod.MULTI_PROFILE_HELP)
    print()
    print(schema_mod.MACHINE_SURFACE_HELP)


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

def cmd_teams(args, config):
    pretty = False
    while args:
        flag, args = args[0], args[1:]
        if flag == '--pretty':
            pretty = True
        else:
            raise UsageError(f'Unknown flag: {flag}')
    debug = _debug_enabled(config)
    access_token, base = auth_mod.graph_setup(config, debug=debug)
    data = api_mod.graph_get(base, teams_mod.joined_teams_endpoint(), access_token, debug=debug)
    if data is None:
        return 1
    rows = teams_mod.normalize_teams(data)
    print(format_teams_pretty(rows) if pretty else json.dumps(rows))
    return 0


def cmd_channels(args, config):
    team, args = schema_mod.pop_positional_id(args)
    pretty = False
    while args:
        flag, args = args[0], args[1:]
        if flag == '--team':
            team, args = _require_value(flag, args)
        elif flag == '--pretty':
            pretty = True
        else:
            raise UsageError(f'Unknown flag: {flag}')
    if not team:
        raise UsageError('channels requires --team <team-id> (or a bare positional id)')
    debug = _debug_enabled(config)
    access_token, base = auth_mod.graph_setup(config, debug=debug)
    data = api_mod.graph_paginate(base, teams_mod.channels_endpoint(team), access_token, debug=debug)
    if data is None:
        return 1
    rows = teams_mod.normalize_channels(data)
    print(format_channels_pretty(rows) if pretty else json.dumps(rows))
    return 0


def cmd_chats(args, config):
    chat_type = ''
    pretty = False
    while args:
        flag, args = args[0], args[1:]
        if flag == '--type':
            chat_type, args = _require_value(flag, args)
        elif flag == '--pretty':
            pretty = True
        else:
            raise UsageError(f'Unknown flag: {flag}')
    debug = _debug_enabled(config)
    access_token, base = auth_mod.graph_setup(config, debug=debug)
    data = api_mod.graph_paginate(base, teams_mod.chats_endpoint(), access_token, debug=debug)
    if data is None:
        return 1
    rows = teams_mod.normalize_chats(data, chat_type=chat_type)
    print(format_chats_pretty(rows) if pretty else json.dumps(rows))
    return 0


def cmd_messages(args, config):
    channel = chat = team = since = ''
    limit = 4
    pretty = include_system = False
    while args:
        flag, args = args[0], args[1:]
        if flag == '--channel':
            channel, args = _require_value(flag, args)
        elif flag == '--chat':
            chat, args = _require_value(flag, args)
        elif flag == '--team':
            team, args = _require_value(flag, args)
        elif flag == '--since':
            since, args = _require_value(flag, args)
        elif flag == '--limit':
            limit, args = _require_int(flag, args)
            limit = max(1, min(limit, 50))
        elif flag == '--all':
            include_system = True
        elif flag == '--pretty':
            pretty = True
        else:
            raise UsageError(f'Unknown flag: {flag}')
    if bool(channel) == bool(chat):
        raise UsageError('messages requires exactly one of --channel <id> or --chat <id>')

    since_dt = None
    if since:
        since_dt = teams_mod.parse_iso(since)
        if since_dt is None:
            raise UsageError(f'--since requires an ISO-8601 timestamp, got: {since}')

    debug = _debug_enabled(config)
    access_token, base = auth_mod.chatsvc_setup(config, debug=debug)
    conversation_id = channel or chat
    raw = api_mod.chatsvc_messages(
        base, conversation_id, access_token,
        page_size=_page_size(config), max_pages=limit, since_dt=since_dt, debug=debug,
    )
    if raw is None:
        return 1
    if channel:
        rows = teams_mod.normalize_channel_messages(
            raw, team_id=team, channel_id=channel, include_system=include_system,
        )
    else:
        rows = teams_mod.normalize_chat_messages(
            raw, chat_id=chat, include_system=include_system,
        )
    print(format_messages_pretty(rows) if pretty else json.dumps(rows))
    return 0


def cmd_config(args, config):
    profile = region = page_size = ''
    while args:
        flag, args = args[0], args[1:]
        if flag == '--profile':
            profile, args = _require_value(flag, args)
        elif flag == '--region':
            region, args = _require_value(flag, args)
        elif flag == '--page-size':
            page_size, args = _require_value(flag, args)
        else:
            raise UsageError(f'Unknown flag: {flag}')

    changed = False
    if profile:
        config_mod.config_set('owa_piggy_profile', profile)
        _info(f'default profile saved: {profile}')
        changed = True
    if region:
        config_mod.config_set('teams_region', region.strip().lower())
        _info(f'teams_region saved: {region.strip().lower()}')
        changed = True
    if page_size:
        config_mod.config_set('page_size', page_size)
        _info(f'page_size saved: {page_size}')
        changed = True
    if changed:
        return 0

    _info(f'Config file: {config_mod.CONFIG_PATH}')
    if config.get('owa_piggy_profile'):
        _info(f"  owa_piggy_profile={config.get('owa_piggy_profile')}")
    else:
        _info('  owa_piggy_profile=(not set - owa-piggy picks its default)')
    _info(f"  teams_region={config.get('teams_region') or '(not set - default emea)'}")
    _info(f"  page_size={config.get('page_size') or '(not set - default 50)'}")
    return 0


def cmd_refresh(args, config):
    if args:
        raise UsageError(f'Unknown flag: {args[0]}')
    _info('Refreshing token...')
    debug = _debug_enabled(config)
    try:
        access_token, base = auth_mod.graph_setup(config, debug=debug)
    except OwaError as error:
        return emit_error(error)
    me = api_mod.graph_get(base, 'me?$select=displayName,userPrincipalName', access_token, debug=debug)
    if not isinstance(me, dict):
        _error('Auth verification failed.')
        return 1
    if me.get('userPrincipalName'):
        _info(f"Connected to Graph as {me.get('displayName')} ({me['userPrincipalName']})")
    return 0


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

AUTHED_COMMANDS = {'teams', 'channels', 'chats', 'messages'}

_TEAMS_FLAGS = [
    schema_mod.flag('--pretty', summary='Human-readable table (default: JSON)'),
]

_CHANNELS_FLAGS = [
    schema_mod.flag('--team', value='<team-id>', summary='Team id (flag or positional)'),
    schema_mod.flag('--pretty', summary='Human-readable table (default: JSON)'),
]

_CHATS_FLAGS = [
    schema_mod.flag('--type', value='<oneOnOne|group|meeting>', summary='Filter by chat type'),
    schema_mod.flag('--pretty', summary='Human-readable table (default: JSON)'),
]

_MESSAGES_FLAGS = [
    schema_mod.flag('--channel', value='<conv-id>', summary='Channel conversation id (threaded)'),
    schema_mod.flag('--chat', value='<conv-id>', summary='Chat conversation id (flat)'),
    schema_mod.flag('--team', value='<team-id>', summary='Team id, echoed into channel metadata'),
    schema_mod.flag('--since', value='<iso>', summary='Only messages at/after this ISO-8601 time (stops paging older)'),
    schema_mod.flag('--limit', value='<n>', summary='Max pages to fetch (default 4)'),
    schema_mod.flag('--all', summary='Include system events and empty bodies'),
    schema_mod.flag('--pretty', summary='Human-readable view (default: JSON)'),
]

_CONFIG_FLAGS = [
    schema_mod.flag('--profile', value='<alias>', summary='Pin a default owa-piggy profile alias'),
    schema_mod.flag('--region', value='<region>', summary='Pin the chatsvc region (emea/amer/...)'),
    schema_mod.flag('--page-size', value='<n>', summary='Pin the chatsvc page size (max 50)'),
]

COMMAND_SCHEMA = [
    schema_mod.command('teams', 'List my joined teams', auth='graph', flags=_TEAMS_FLAGS, aliases=['ls']),
    schema_mod.command('channels', "List a team's channels", auth='graph', flags=_CHANNELS_FLAGS),
    schema_mod.command('chats', 'List my chats', auth='graph', flags=_CHATS_FLAGS),
    schema_mod.command('messages', 'Read channel or chat messages', auth='ic3', flags=_MESSAGES_FLAGS),
    schema_mod.command('refresh', 'Force a token refresh', auth='graph'),
    schema_mod.command('config', 'View or update configuration', mutates=True, flags=_CONFIG_FLAGS),
]

_HANDLERS = {
    'teams': cmd_teams,
    'channels': cmd_channels,
    'chats': cmd_chats,
    'messages': cmd_messages,
}


def _main(argv):
    handled = schema_mod.maybe_emit_schema(argv, tool='owa-teams', commands=COMMAND_SCHEMA)
    if handled is not None:
        return handled

    if not argv:
        print_help()
        return 0
    if argv[0] in ('help', '--help', '-h'):
        print_help()
        return 0
    if argv[0] in ('--version', '-v'):
        print(f'owa-teams {__version__}')
        return 0

    debug_flag = False
    profile_override = ''
    # Strip global flags (--debug/--verbose, --profile) from anywhere in argv.
    # Exception: on `owa-teams config`, --profile is a subcommand flag.
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
    cmd = schema_mod.resolve_alias(cmd, COMMAND_SCHEMA)

    help_rc = schema_mod.maybe_emit_subcommand_help(
        cmd, rest, tool='owa-teams', commands=COMMAND_SCHEMA,
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
        raise UsageError(f"Unknown command: {cmd}. Run 'owa-teams help' for usage.")

    schema_mod.precheck_required_args(cmd, rest, commands=COMMAND_SCHEMA)
    return _HANDLERS[cmd](rest, config)


def main(argv=None):
    return mode_mod.run_with_output_modes(
        'owa-teams', sys.argv[1:] if argv is None else argv, _main,
    )
