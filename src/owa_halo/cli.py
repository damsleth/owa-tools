"""Argument parsing for `owa-halo`."""

import json
import os
import re
import sys
from pathlib import Path

from owa_core import modes as mode_mod
from owa_core import schema as schema_mod
from owa_core.errors import ConflictError, InternalError, UsageError, _require_value

from . import __version__
from . import api as api_mod
from . import auth as auth_mod
from . import ticket as ticket_mod


def _debug_enabled(config):
    return bool(config.get('debug')) or os.environ.get('HALO_DEBUG') == '1'


def print_help():
    print("""owa-halo - read-only HaloITSM tickets

Usage: owa-halo <command> <ticket-id|ticket-url> [options]

Commands:
  ticket        Ticket, status, all metadata and every action/comment
  attachments   List attachments and inline screenshots; --out downloads them
  schema        Print machine-readable command schema

Options:
  --all              Include Halo system actions (ticket)
  --out <dir>        Download attachments and inline images into <dir>
  --pretty           Human-readable output
  --profile <alias>  owa-piggy profile with Halo (default: the default or only one)
""")
    print(schema_mod.MULTI_PROFILE_HELP)
    print()
    print(schema_mod.MACHINE_SURFACE_HELP)


def _parse(args, flags):
    """Return (ticket_ref, opts) for a command's positional + flags."""
    ref = None
    opts = {}
    while args:
        flag, args = args[0], args[1:]
        if flag in ('--pretty', '--all') and flag in flags:
            opts[flag] = True
        elif flag == '--out' and flag in flags:
            opts[flag], args = _require_value(flag, args)
        elif flag.startswith('-'):
            raise UsageError(f'Unknown flag: {flag}')
        elif ref is None:
            ref = flag
        else:
            raise UsageError(f'Unexpected argument: {flag}')
    if ref is None:
        raise UsageError('ticket id or URL required')
    return ref, opts


def _ticket_id(ref, base):
    ticket_id, host = ticket_mod.parse_ticket_ref(ref)
    if host and host.lower() != base.split('://', 1)[1].lower():
        raise UsageError(f'ticket is on {host}, but this profile is {base}')
    return ticket_id


def _load(ticket_id, token, base, *, include_system, debug):
    ticket = api_mod.get_ticket(base, token, ticket_id, debug=debug)
    actions = api_mod.get_actions(base, token, ticket_id, include_system=include_system, debug=debug)
    got, total = len((actions or {}).get('actions') or []), (actions or {}).get('record_count')
    if isinstance(total, int) and total > got:
        # ponytail: one unpaged request; add page_no/page_size paging if Halo ever truncates
        print(f'WARNING: Halo returned {got} of {total} actions', file=sys.stderr)
    attachments = api_mod.get_attachments(base, token, ticket_id, debug=debug)
    statuses = api_mod.get_statuses(base, token, debug=debug)
    return ticket_mod.build_ticket(ticket, actions, attachments, statuses, base=base)


def cmd_ticket(args, config, token, base):
    ref, opts = _parse(args, {'--pretty', '--all'})
    out, _images = _load(_ticket_id(ref, base), token, base,
                         include_system=opts.get('--all', False), debug=_debug_enabled(config))
    if opts.get('--pretty'):
        print(ticket_mod.format_ticket(out))
    else:
        print(json.dumps(out, ensure_ascii=False))
    return 0


def _safe_name(name):
    return re.sub(r'[^A-Za-z0-9._-]+', '_', name).strip('._') or 'file'


def _write_new(path, data):
    try:
        with open(path, 'xb') as fh:
            fh.write(data)
    except FileExistsError as exc:
        raise ConflictError(f'{path} already exists; not overwriting') from exc


def cmd_attachments(args, config, token, base):
    ref, opts = _parse(args, {'--pretty', '--out'})
    debug = _debug_enabled(config)
    ticket_id = _ticket_id(ref, base)
    out, images = _load(ticket_id, token, base, include_system=True, debug=debug)
    rows = [{'kind': 'attachment', **a} for a in out['attachments']]
    rows += [{'kind': 'image', **{k: v for k, v in img.items() if k != 'url'}} for img in images]
    if opts.get('--out'):
        target = Path(opts['--out']).expanduser()
        target.mkdir(parents=True, exist_ok=True)
        for row, img in zip(rows[len(out['attachments']):], images):
            data = api_mod.fetch_unauthenticated(img['url'], debug=debug)
            ext = '.png' if data[:8] == b'\x89PNG\r\n\x1a\n' else '.jpg' if data[:2] == b'\xff\xd8' else '.bin'
            row['path'] = str(target / f'{ticket_id}-image-{row["n"]}{ext}')
            _write_new(row['path'], data)
        for row in rows[:len(out['attachments'])]:
            link = api_mod.attachment_link(base, token, row['id'], debug=debug)
            if not link:
                raise InternalError(f'Halo returned no download link for attachment {row["id"]}')
            row['path'] = str(target / f'{ticket_id}-{row["id"]}-{_safe_name(row.get("filename", ""))}')
            _write_new(row['path'], api_mod.fetch_unauthenticated(link, debug=debug))
    if opts.get('--pretty'):
        for row in rows:
            label = row.get('filename') or f'inline image {row["n"]} ({row["source"]})'
            print(f'{row["kind"]:10} {label}' + (f'  -> {row["path"]}' if row.get('path') else ''))
    else:
        print(json.dumps(rows, ensure_ascii=False))
    return 0


COMMANDS = {'ticket': cmd_ticket, 'attachments': cmd_attachments}

_REF = schema_mod.flag('<ticket>', summary='Ticket id or https://<tenant>.haloitsm.com/ticket?id=N URL', required=True)
_PRETTY = schema_mod.flag('--pretty', summary='Human-readable output')

COMMAND_SCHEMA = [
    schema_mod.command('ticket', 'Ticket, status, metadata and actions', auth=auth_mod.AUDIENCE, flags=[
        _REF, schema_mod.flag('--all', summary='Include Halo system actions'), _PRETTY,
    ]),
    schema_mod.command('attachments', 'List attachments and inline screenshots', auth=auth_mod.AUDIENCE, flags=[
        _REF, schema_mod.flag('--out', value='<dir>', summary='Download into <dir>; never overwrites'), _PRETTY,
    ]),
]


def _main(argv):
    handled = schema_mod.maybe_emit_schema(argv, tool='owa-halo', commands=COMMAND_SCHEMA)
    if handled is not None:
        return handled
    if not argv or argv[0] in ('help', '--help', '-h'):
        print_help()
        return 0
    if argv[0] in ('--version', '-v'):
        print(f'owa-halo {__version__}')
        return 0

    config = {}
    filtered = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ('--debug', '--verbose'):
            config['debug'] = True
        elif a in ('--profile', '-p'):
            if i + 1 >= len(argv):
                raise UsageError('--profile requires a value')
            config['owa_piggy_profile'] = argv[i + 1]
            i += 1
        else:
            filtered.append(a)
        i += 1
    if not filtered:
        print_help()
        return 0

    cmd, rest = filtered[0], filtered[1:]
    help_rc = schema_mod.maybe_emit_subcommand_help(cmd, rest, tool='owa-halo', commands=COMMAND_SCHEMA)
    if help_rc is not None:
        return help_rc
    if cmd not in COMMANDS:
        raise UsageError(f'Unknown command: {cmd}')
    schema_mod.precheck_required_args(cmd, rest, commands=COMMAND_SCHEMA)
    token, base = auth_mod.setup_auth(config, debug=_debug_enabled(config))
    return COMMANDS[cmd](rest, config, token, base)


def main(argv=None):
    return mode_mod.run_with_output_modes(
        'owa-halo',
        sys.argv[1:] if argv is None else argv,
        _main,
        commands=COMMAND_SCHEMA,
        service=auth_mod.SERVICE,
    )
