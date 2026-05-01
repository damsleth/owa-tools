"""Argument parsing and dispatch for the `owa-mail` command.

owa-mail is pipe-friendly: JSON on stdout, logs on stderr. --pretty
switches stdout to a human-readable view. Exit codes follow POSIX
convention (0 success, 1 error).

Subcommands are parsed manually (no argparse subparsers) to keep the
code flat and to match the layout used by sibling tools owa-cal /
owa-piggy. Each cmd_* fn is responsible for its own flag loop.
"""
import json
import os
import sys

from . import api as api_mod
from . import auth as auth_mod
from . import config as config_mod
from . import folders as folders_mod
from . import messages as messages_mod
from .dates import resolve_date
from .format import (
    format_folders_pretty,
    format_message_pretty,
    format_messages_pretty,
)


def _error(msg):
    print(f'ERROR: {msg}', file=sys.stderr)


def _info(msg):
    print(msg, file=sys.stderr)


def _debug_enabled(config):
    return bool(config.get('debug')) or os.environ.get('MAIL_DEBUG') == '1'


def _split_globals(argv):
    """Pull --debug/--verbose and --profile out of argv.

    --profile is consumed as a global override unless it appears after the
    `config` subcommand (where `config --profile <alias>` is the subcommand's
    own flag for setting the persisted profile).

    Returns (debug, profile, remaining, error). `error` is None on success
    or a string describing a malformed flag.
    """
    debug = False
    profile = ''
    seen_cmd = ''
    out = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ('--debug', '--verbose'):
            debug = True
            i += 1
            continue
        if a == '--profile' and seen_cmd != 'config':
            if i + 1 >= len(argv):
                return debug, profile, out, '--profile requires a value'
            profile = argv[i + 1]
            i += 2
            continue
        if not seen_cmd and not a.startswith('-'):
            seen_cmd = a
        out.append(a)
        i += 1
    return debug, profile, out, None


def print_help():
    print("""owa-mail - Mail CLI for Outlook / Microsoft 365

Usage: owa-mail <command> [options]

Global options:
  --debug, --verbose   Print HTTP requests and response bodies on errors
                       (also: MAIL_DEBUG=1)
  --profile <alias>    Forward to owa-piggy as --profile <alias> for
                       this invocation (overrides owa_piggy_profile in
                       the config file, and OWA_PROFILE in the env)

Commands:
  messages             List messages (default: Inbox, last 25)
  show                 Show full message body by --id
  send                 Compose and send a new message
  reply                Reply to a message by --id
  reply-all            Reply-all to a message by --id
  forward              Forward a message by --id
  delete               Delete a message by --id
  move                 Move a message to another folder
  mark                 Mark a message read/unread/flagged
  folders              List mail folders
  refresh              Force a token refresh and verify auth
  config               View or update configuration
  help                 Show this help

messages options:
  --folder <name|id>   Inbox|Drafts|SentItems|DeletedItems|Junk|Archive
  --unread             Only unread messages
  --from <addr>        Sender substring filter
  --subject <text>     Subject substring filter
  --search <kql>       KQL search (mutually exclusive with filters)
  --since <date>       ReceivedDateTime >= date (YYYY-MM-DD or today/yesterday)
  --until <date>       ReceivedDateTime <= date
  --limit <n>          Max results (default 25, hard cap 200)
  --pretty             Human-readable table (default: JSON)

show options:
  --id <message-id>    (required)
  --pretty             Human-readable header block + body

send options:
  --to <addr[,addr]>   (required) one or more recipients
  --cc <addr[,addr]>
  --bcc <addr[,addr]>
  --subject <text>     (required)
  --body <text>        Body content (use - to read from stdin)
  --html               Treat --body as HTML
  --send-at <iso>      Schedule deferred delivery (ISO datetime, UTC if naive)
  --save-draft         Save as Draft instead of sending
  --importance <lvl>   low|normal|high

reply / reply-all / forward options:
  --id <message-id>    (required)
  --body <text>        Reply text (use - to read from stdin)
  --html               Treat --body as HTML
  --send-at <iso>      Schedule deferred delivery
  --to <addr[,addr]>   (forward only) recipients
  --save-draft

delete options:
  --id <message-id>    (required)
  --confirm            Skip confirmation prompt

move options:
  --id <message-id>    (required)
  --to <folder>        (required) well-known name or folder id

mark options:
  --id <message-id>    (required)
  --read | --unread    Toggle IsRead
  --flag | --unflag    Toggle FlagStatus

folders options:
  --pretty             Human-readable table

config options:
  --profile <alias>    Pin an owa-piggy profile alias (owa_piggy_profile)
  --app-client-id <id> Set app registration client ID (optional)

Auth:
  Default path: owa-mail shells out to owa-piggy for a fresh access
  token on every call. owa-piggy owns the refresh token; owa-mail
  stores only an optional profile alias.

  App-registration path: set OUTLOOK_APP_CLIENT_ID (plus
  OUTLOOK_REFRESH_TOKEN and OUTLOOK_TENANT_ID) in
  ~/.config/owa-mail/config and owa-mail talks to the AAD token
  endpoint directly.

  Quickstart:
    brew install damsleth/tap/owa-piggy
    owa-piggy setup                            # or: setup --profile work

Examples:
  owa-mail messages --pretty
  owa-mail messages --unread --limit 10 --pretty
  owa-mail messages --folder SentItems --since 2026-04-01 --pretty
  owa-mail show --id AAMkAG... --pretty
  owa-mail send --to a@example.com --subject hi --body "hello"
  owa-mail send --to a@example.com --subject later --body x --send-at 2026-05-01T09:00:00Z
  owa-mail reply --id AAMkAG... --body "thanks"
  owa-mail mark --id AAMkAG... --read
  owa-mail move --id AAMkAG... --to Archive
  owa-mail folders --pretty""")


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


def _read_body(value):
    """If `--body -` was given, slurp stdin. Otherwise return as-is."""
    if value == '-':
        return sys.stdin.read()
    return value


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

def cmd_messages(args, config, access_token, api_base):
    folder = ''
    unread = False
    pretty = False
    sender = subject_q = search = since = until = ''
    limit = 25
    while args:
        flag, args = args[0], args[1:]
        if flag == '--folder':
            folder, args = _require_value(flag, args)
        elif flag == '--unread':
            unread = True
        elif flag == '--from':
            sender, args = _require_value(flag, args)
        elif flag == '--subject':
            subject_q, args = _require_value(flag, args)
        elif flag == '--search':
            search, args = _require_value(flag, args)
        elif flag == '--since':
            v, args = _require_value(flag, args); since = resolve_date(v)
        elif flag == '--until':
            v, args = _require_value(flag, args); until = resolve_date(v)
        elif flag == '--limit':
            limit, args = _require_int(flag, args)
        elif flag == '--pretty':
            pretty = True
        else:
            _error(f'Unknown flag: {flag}'); sys.exit(1)

    if limit < 1:
        _error('--limit must be >= 1'); return 1
    if limit > 200:
        limit = 200

    if search and (unread or sender or subject_q or since or until):
        _error('--search cannot be combined with --unread/--from/--subject/--since/--until '
               '(Outlook REST: $search and $filter are mutually exclusive)')
        return 1

    debug = _debug_enabled(config)
    path = folders_mod.folder_messages_path(folder)

    params = messages_mod.build_list_query(
        unread=unread, sender=sender, subject_q=subject_q, search=search,
        since=since, until=until, limit=limit,
    )
    q = api_mod.build_query(params)
    data = api_mod.api_get(api_base, f'{path}?{q}', access_token, debug=debug)
    if data is None:
        return 1
    flat = messages_mod.normalize_messages(data)
    if pretty:
        print(format_messages_pretty(flat))
    else:
        print(json.dumps(flat))
    return 0


def cmd_show(args, config, access_token, api_base):
    message_id = ''
    pretty = False
    while args:
        flag, args = args[0], args[1:]
        if flag == '--id':
            message_id, args = _require_value(flag, args)
        elif flag == '--pretty':
            pretty = True
        else:
            _error(f'Unknown flag: {flag}'); sys.exit(1)
    if not message_id:
        _error('--id is required'); return 1

    debug = _debug_enabled(config)
    q = api_mod.build_query({'$select': messages_mod.SHOW_SELECT})
    raw = api_mod.api_get(
        api_base, f'{messages_mod.message_path(message_id)}?{q}', access_token, debug=debug
    )
    if raw is None:
        return 1
    flat = messages_mod.normalize_message(raw)
    if pretty:
        print(format_message_pretty(flat))
    else:
        print(json.dumps(flat))
    return 0


def _parse_send_flags(args, allow_to=True, allow_cc_bcc=True, allow_importance=True):
    """Shared flag loop for send / reply / reply-all / forward.

    Returns a dict of parsed options. Callers opt specific flags in so
    unsupported combinations fail fast instead of being silently
    ignored.
    """
    out = {
        'id': '',
        'to': '',
        'cc': '',
        'bcc': '',
        'subject': '',
        'body': None,
        'html': False,
        'send_at': '',
        'save_draft': False,
        'importance': '',
    }
    while args:
        flag, args = args[0], args[1:]
        if flag == '--id':
            out['id'], args = _require_value(flag, args)
        elif flag == '--to' and allow_to:
            out['to'], args = _require_value(flag, args)
        elif flag == '--cc' and allow_cc_bcc:
            out['cc'], args = _require_value(flag, args)
        elif flag == '--bcc' and allow_cc_bcc:
            out['bcc'], args = _require_value(flag, args)
        elif flag == '--subject':
            out['subject'], args = _require_value(flag, args)
        elif flag == '--body':
            v, args = _require_value(flag, args); out['body'] = _read_body(v)
        elif flag == '--html':
            out['html'] = True
        elif flag == '--send-at':
            out['send_at'], args = _require_value(flag, args)
        elif flag == '--save-draft':
            out['save_draft'] = True
        elif flag == '--importance' and allow_importance:
            out['importance'], args = _require_value(flag, args)
        else:
            _error(f'Unknown flag: {flag}'); sys.exit(1)
    return out


def cmd_send(args, config, access_token, api_base):
    opts = _parse_send_flags(
        args, allow_to=True, allow_cc_bcc=True, allow_importance=True
    )
    debug = _debug_enabled(config)

    try:
        msg = messages_mod.build_message_body(
            to=opts['to'], cc=opts['cc'], bcc=opts['bcc'],
            subject=opts['subject'], body=opts['body'],
            html=opts['html'], importance=opts['importance'],
        )
    except ValueError as e:
        _error(str(e)); return 1

    # Path A: immediate send, no draft, no scheduling.
    if not opts['send_at'] and not opts['save_draft']:
        result = api_mod.api_request(
            'POST', api_base, 'me/sendMail', access_token,
            body=messages_mod.build_send_payload(msg), debug=debug,
        )
        if result is None:
            return 1
        # sendMail returns 204 (empty body); api.api_request normalises to {}.
        print(json.dumps({'sent': True}))
        return 0

    # Path B: create a draft, optionally with scheduled-send extended prop.
    try:
        draft_payload = messages_mod.build_draft_payload(msg, send_at=opts['send_at'])
    except ValueError as e:
        _error(str(e)); return 1
    draft = api_mod.api_request(
        'POST', api_base, 'me/messages', access_token,
        body=draft_payload, debug=debug,
    )
    if not draft:
        return 1
    draft_flat = messages_mod.normalize_message(draft)

    if opts['save_draft']:
        print(json.dumps(draft_flat))
        return 0

    # Send the draft. Scheduled drafts are sent immediately by
    # /send too - Exchange Transport then holds them in Outbox until
    # the deferred time.
    result = api_mod.api_request(
        'POST', api_base, f'{messages_mod.message_path(draft_flat["id"])}/send',
        access_token, debug=debug,
    )
    if result is None:
        return 1
    print(json.dumps({'sent': True, 'id': draft_flat['id'], 'send_at': opts['send_at'] or None}))
    return 0


def _reply_like(args, config, access_token, api_base, action):
    """Shared body for reply / reply-all / forward.

    `action` is one of 'createReply', 'createReplyAll', 'createForward'.
    """
    allow_to = (action == 'createForward')
    opts = _parse_send_flags(
        args,
        allow_to=allow_to,
        allow_cc_bcc=False,
        allow_importance=False,
    )
    if not opts['id']:
        _error('--id is required'); return 1
    if not opts['save_draft'] and opts['body'] is None:
        _error('--body is required (or pass --save-draft to create an empty draft)')
        return 1
    if action == 'createForward' and not opts['save_draft'] and not opts['to']:
        _error('forward requires --to (or --save-draft)'); return 1

    debug = _debug_enabled(config)
    draft = api_mod.api_request(
        'POST', api_base, f'{messages_mod.message_path(opts["id"])}/{action}',
        access_token, debug=debug,
    )
    if not draft:
        return 1
    draft_flat = messages_mod.normalize_message(draft)
    draft_id = draft_flat.get('id')
    if not draft_id:
        _error('createReply/Forward returned no draft id'); return 1

    patch = messages_mod.build_reply_patch(
        body=opts['body'], html=opts['html'],
        send_at=opts['send_at'] if not opts['save_draft'] else None,
        extra_to=opts['to'] if action == 'createForward' else None,
    )
    if patch:
        result = api_mod.api_request(
            'PATCH', api_base, messages_mod.message_path(draft_id), access_token,
            body=patch, debug=debug,
        )
        if result is None:
            return 1

    if opts['save_draft']:
        # Re-fetch normalized state after patch.
        latest = api_mod.api_get(
            api_base,
            f'{messages_mod.message_path(draft_id)}?{api_mod.build_query({"$select": messages_mod.LIST_SELECT})}',
            access_token, debug=debug,
        )
        print(json.dumps(messages_mod.normalize_message(latest or draft)))
        return 0

    sent = api_mod.api_request(
        'POST', api_base, f'{messages_mod.message_path(draft_id)}/send',
        access_token, debug=debug,
    )
    if sent is None:
        return 1
    print(json.dumps({'sent': True, 'id': draft_id, 'send_at': opts['send_at'] or None}))
    return 0


def cmd_reply(args, config, access_token, api_base):
    return _reply_like(args, config, access_token, api_base, 'createReply')


def cmd_reply_all(args, config, access_token, api_base):
    return _reply_like(args, config, access_token, api_base, 'createReplyAll')


def cmd_forward(args, config, access_token, api_base):
    return _reply_like(args, config, access_token, api_base, 'createForward')


def cmd_delete(args, config, access_token, api_base):
    message_id = ''
    confirm = False
    while args:
        flag, args = args[0], args[1:]
        if flag == '--id':
            message_id, args = _require_value(flag, args)
        elif flag == '--confirm':
            confirm = True
        else:
            _error(f'Unknown flag: {flag}'); sys.exit(1)
    if not message_id:
        _error('--id is required'); return 1

    debug = _debug_enabled(config)
    if not confirm:
        existing = api_mod.api_get(
            api_base,
            f'{messages_mod.message_path(message_id)}?{api_mod.build_query({"$select":"Id,Subject,From,ReceivedDateTime"})}',
            access_token, debug=debug,
        )
        if existing is None:
            return 1
        flat = messages_mod.normalize_message(existing)
        sys.stderr.write(
            f"\033[33mDelete '{flat.get('subject','')}' "
            f"from {flat.get('from','')} ({flat.get('received','')})? (y/N): \033[0m"
        )
        sys.stderr.flush()
        try:
            answer = input().strip().lower()
        except EOFError:
            answer = ''
        if answer not in ('y', 'yes'):
            _info('Aborted.')
            return 0

    result = api_mod.api_request(
        'DELETE', api_base, messages_mod.message_path(message_id), access_token, debug=debug,
    )
    if result is None:
        return 1
    _info('Deleted.')
    return 0


def cmd_move(args, config, access_token, api_base):
    message_id = ''
    destination = ''
    while args:
        flag, args = args[0], args[1:]
        if flag == '--id':
            message_id, args = _require_value(flag, args)
        elif flag == '--to':
            destination, args = _require_value(flag, args)
        else:
            _error(f'Unknown flag: {flag}'); sys.exit(1)
    if not message_id:
        _error('--id is required'); return 1
    if not destination:
        _error('--to is required (folder name or id)'); return 1

    debug = _debug_enabled(config)
    body = {'DestinationId': folders_mod.resolve_folder_id(destination)}
    result = api_mod.api_request(
        'POST', api_base, f'{messages_mod.message_path(message_id)}/move',
        access_token, body=body, debug=debug,
    )
    if result is None:
        return 1
    print(json.dumps(messages_mod.normalize_message(result)))
    return 0


def cmd_mark(args, config, access_token, api_base):
    message_id = ''
    read = flag_state = None
    while args:
        flag, args = args[0], args[1:]
        if flag == '--id':
            message_id, args = _require_value(flag, args)
        elif flag == '--read':
            if read is False:
                _error('--read and --unread are mutually exclusive'); return 1
            read = True
        elif flag == '--unread':
            if read is True:
                _error('--read and --unread are mutually exclusive'); return 1
            read = False
        elif flag == '--flag':
            if flag_state is False:
                _error('--flag and --unflag are mutually exclusive'); return 1
            flag_state = True
        elif flag == '--unflag':
            if flag_state is True:
                _error('--flag and --unflag are mutually exclusive'); return 1
            flag_state = False
        else:
            _error(f'Unknown flag: {flag}'); sys.exit(1)
    if not message_id:
        _error('--id is required'); return 1
    if read is None and flag_state is None:
        _error('mark requires one of --read, --unread, --flag, --unflag'); return 1

    debug = _debug_enabled(config)
    patch = messages_mod.build_mark_patch(read=read, flag=flag_state)
    result = api_mod.api_request(
        'PATCH', api_base, messages_mod.message_path(message_id), access_token,
        body=patch, debug=debug,
    )
    if result is None:
        return 1
    print(json.dumps(messages_mod.normalize_message(result)))
    return 0


def cmd_folders(args, config, access_token, api_base):
    pretty = False
    while args:
        flag, args = args[0], args[1:]
        if flag == '--pretty':
            pretty = True
        else:
            _error(f'Unknown flag: {flag}'); sys.exit(1)

    debug = _debug_enabled(config)
    q = api_mod.build_query({
        '$select': 'Id,DisplayName,UnreadItemCount,TotalItemCount',
        '$top': 100,
    })
    data = api_mod.api_get(api_base, f'me/MailFolders?{q}', access_token, debug=debug)
    if data is None:
        return 1
    items = folders_mod.normalize_folders(data)
    if pretty:
        print(format_folders_pretty(items))
    else:
        print(json.dumps(items))
    return 0


def cmd_config(args, config):
    """Handled specially: no auth required."""
    profile = app_client_id = ''
    while args:
        flag, args = args[0], args[1:]
        if flag == '--profile':
            profile, args = _require_value(flag, args)
        elif flag == '--app-client-id':
            app_client_id, args = _require_value(flag, args)
        else:
            _error(f'Unknown flag: {flag}'); sys.exit(1)

    wrote = False
    if profile:
        config_mod.config_set('owa_piggy_profile', profile)
        _info(f'owa-piggy profile saved: {profile}'); wrote = True
    if app_client_id:
        config_mod.config_set('OUTLOOK_APP_CLIENT_ID', app_client_id)
        _info('App client ID saved'); wrote = True

    if not wrote:
        _info(f'Config file: {config_mod.CONFIG_PATH}')
        if config.get('owa_piggy_profile'):
            _info(f"  owa_piggy_profile={config.get('owa_piggy_profile')}")
        else:
            _info('  owa_piggy_profile=(not set - owa-piggy picks its default)')
        if config.get('OUTLOOK_APP_CLIENT_ID'):
            _info(f"  OUTLOOK_APP_CLIENT_ID={config.get('OUTLOOK_APP_CLIENT_ID')} (app registration)")
        else:
            _info('  OUTLOOK_APP_CLIENT_ID=(not set - using owa-piggy)')
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

AUTHED_HANDLERS = {
    'messages': cmd_messages,
    'show': cmd_show,
    'send': cmd_send,
    'reply': cmd_reply,
    'reply-all': cmd_reply_all,
    'forward': cmd_forward,
    'delete': cmd_delete,
    'move': cmd_move,
    'mark': cmd_mark,
    'folders': cmd_folders,
}


def main():
    argv = sys.argv[1:]

    if not argv:
        print_help()
        return 0
    if argv[0] in ('help', '--help', '-h'):
        print_help()
        return 0

    debug_flag, profile_override, argv, err = _split_globals(argv)
    if err:
        _error(err); return 1

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

    handler = AUTHED_HANDLERS.get(cmd)
    if handler is None:
        _error(f"Unknown command: {cmd}. Run 'owa-mail help' for usage.")
        return 1

    access_token, api_base = auth_mod.setup_auth(
        config, debug=_debug_enabled(config)
    )
    return handler(rest, config, access_token, api_base)
