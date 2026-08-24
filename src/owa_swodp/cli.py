"""Command-line interface for SWODP timesheet data."""

from __future__ import annotations

import json
import os
import sys

from owa_core import modes as mode_mod
from owa_core import schema as schema_mod
from owa_core import tty as tty_mod
from owa_core.errors import AuthExpiredError, ConflictError, UsageError, _require_value

from . import __version__, service
from . import session as session_mod

TOOL = "owa-swodp"


def print_help():
    print(
        """owa-swodp - SWODP ServiceNow timesheet data layer

Usage: owa-swodp <command> [options]

Session commands:
  status       Verify the dedicated Edge sidecar and Table API session.
  setup        Open visible Edge for one-time/recovery sign-in.
  reseed       Verify a silent headless sign-in using the existing profile.

Read commands:
  sync         Fetch week cards plus history, allocations, and categories.
  cards        Fetch time cards in a range around a Monday.
  history      Fetch full time-card activity history.
  allocations Fetch allocations from the last 90 days (or --since).
  categories  Build display-name -> raw-value Other category map.
  task         Look up a task by task number.

Write command:
  write        Apply a validated JSON row plan to Pending cards only.

Common options:
  --instance <prod|uat>  Target instance (default: prod). Separate Edge profile per instance.
  --pretty               Indented human-readable JSON.
  --debug                Diagnostics to stderr (also OWA_SWODP_DEBUG=1).

Examples:
  owa-swodp status --json
  owa-swodp sync --week-start 2026-08-17
  owa-swodp cards --week-start 2026-08-17 --range-weeks 3
  owa-swodp write --instance uat --week-start 2026-08-17 --file rows.json --confirm
"""
    )
    print(schema_mod.MACHINE_SURFACE_HELP)


def _common(args, *, allow_pretty=True):
    instance = "prod"
    pretty = False
    debug = os.environ.get("OWA_SWODP_DEBUG") == "1"
    rest = []
    while args:
        flag, args = args[0], args[1:]
        if flag == "--instance":
            instance, args = _require_value(flag, args)
        elif flag == "--pretty" and allow_pretty:
            pretty = True
        elif flag == "--json":
            pass
        elif flag in ("--debug", "--verbose"):
            debug = True
        else:
            rest.append(flag)
    session_mod.validate_instance(instance)
    return instance, pretty, debug, rest


def _emit(value, pretty=False):
    print(json.dumps(value, ensure_ascii=False, indent=2 if pretty else None))


def _capture(instance, debug, *, visible=False):
    log = (lambda message: print(f"DEBUG: {message}", file=sys.stderr)) if debug else None
    return session_mod.capture(instance, visible=visible, log=log)


def cmd_status(args):
    instance, pretty, debug, rest = _common(args)
    if rest:
        raise UsageError(f"Unknown flag: {rest[0]}")
    directory = session_mod.profile_dir(instance)
    if not directory.is_dir():
        raise AuthExpiredError(
            f"SWODP {instance} sidecar profile is not configured",
            remediation=f"Run: owa-swodp setup --instance {instance}",
        )
    captured = _capture(instance, debug)
    rows = service.probe(captured, debug=debug)
    _emit(
        {
            "ok": True,
            "instance": instance,
            "host": captured.host,
            "user": captured.user,
            "profile_dir": str(directory),
            "probe_rows": rows,
        },
        pretty,
    )
    return 0


def cmd_setup(args, *, visible):
    instance, pretty, debug, rest = _common(args)
    if rest:
        raise UsageError(f"Unknown flag: {rest[0]}")
    if visible:
        print("Complete SWODP sign-in in the Edge window; it will close when ready.", file=sys.stderr)
    captured = _capture(instance, debug, visible=visible)
    _emit({"ok": True, "instance": instance, "host": captured.host, "user": captured.user}, pretty)
    return 0


def _parse_read(args, *, week=False, range_weeks=False, since=False):
    instance, pretty, debug, rest = _common(args)
    week_start = since_value = ""
    weeks = 3
    remaining = []
    while rest:
        flag, rest = rest[0], rest[1:]
        if week and flag == "--week-start":
            week_start, rest = _require_value(flag, rest)
        elif range_weeks and flag == "--range-weeks":
            raw, rest = _require_value(flag, rest)
            try:
                weeks = int(raw)
            except ValueError as exc:
                raise UsageError("--range-weeks requires an integer") from exc
        elif since and flag == "--since":
            since_value, rest = _require_value(flag, rest)
        else:
            remaining.append(flag)
    if remaining:
        raise UsageError(f"Unknown flag: {remaining[0]}")
    if week and not week_start:
        raise UsageError("--week-start is required")
    return instance, pretty, debug, week_start, weeks, since_value


def cmd_sync(args):
    cards_only = "--cards-only" in args
    args = [arg for arg in args if arg != "--cards-only"]
    instance, pretty, debug, week_start, weeks, _ = _parse_read(
        args, week=True, range_weeks=True
    )
    captured = _capture(instance, debug)
    _emit(service.sync(captured, week_start, weeks=weeks, cards_only=cards_only, debug=debug), pretty)
    return 0


def cmd_cards(args):
    instance, pretty, debug, week_start, weeks, _ = _parse_read(
        args, week=True, range_weeks=True
    )
    captured = _capture(instance, debug)
    _emit(service.week_cards(captured, week_start, weeks=weeks, debug=debug), pretty)
    return 0


def cmd_history(args):
    instance, pretty, debug, _, _, _ = _parse_read(args)
    _emit(service.history(_capture(instance, debug), debug=debug), pretty)
    return 0


def cmd_allocations(args):
    instance, pretty, debug, _, _, since = _parse_read(args, since=True)
    _emit(service.allocations(_capture(instance, debug), since=since or None, debug=debug), pretty)
    return 0


def cmd_categories(args):
    instance, pretty, debug, _, _, _ = _parse_read(args)
    _emit(service.categories(_capture(instance, debug), debug=debug), pretty)
    return 0


def cmd_task(args):
    instance, pretty, debug, rest = _common(args)
    task_number = ""
    while rest:
        flag, rest = rest[0], rest[1:]
        if flag == "--number":
            task_number, rest = _require_value(flag, rest)
        elif not flag.startswith("-") and not task_number:
            task_number = flag
        else:
            raise UsageError(f"Unknown argument: {flag}")
    if not task_number:
        raise UsageError("task number is required")
    _emit(service.task_lookup(_capture(instance, debug), task_number, debug=debug), pretty)
    return 0


def _load_rows(path):
    try:
        text = sys.stdin.read() if path == "-" else open(path, encoding="utf-8").read()
        rows = json.loads(text)
    except OSError as exc:
        raise UsageError(f"could not read write plan: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise UsageError(f"write plan is not valid JSON: {exc}") from exc
    return service.validate_write_rows(rows)


def cmd_write(args):
    instance, pretty, debug, rest = _common(args)
    week_start = path = ""
    confirmed = False
    while rest:
        flag, rest = rest[0], rest[1:]
        if flag == "--week-start":
            week_start, rest = _require_value(flag, rest)
        elif flag == "--file":
            path, rest = _require_value(flag, rest)
        elif flag in ("--confirm", "--yes"):
            confirmed = True
        else:
            raise UsageError(f"Unknown flag: {flag}")
    if not week_start:
        raise UsageError("--week-start is required")
    if not path:
        raise UsageError("--file is required")
    service.parse_iso_date(week_start, name="week start")
    rows = _load_rows(path)
    if not tty_mod.confirm(
        f"Write {len(rows)} row(s) to SWODP {instance}? [y/N] ",
        confirm=confirmed,
    ):
        raise UsageError("write cancelled")
    results = service.write_week(_capture(instance, debug), week_start, rows, debug=debug)
    failures = [row for row in results if row["action"] in {"failed", "skipped"}]
    _emit({"ok": not failures, "instance": instance, "results": results}, pretty)
    if failures:
        raise ConflictError(f"{len(failures)} SWODP write operation(s) failed or were skipped")
    return 0


_INSTANCE = schema_mod.flag("--instance", value="<prod|uat>", summary="Target instance (default: prod)")
_PRETTY = schema_mod.flag("--pretty", summary="Indented human-readable JSON")
_DEBUG = schema_mod.flag("--debug", summary="Diagnostics to stderr")
_COMMON = [_INSTANCE, _PRETTY, _DEBUG]
_WEEK = schema_mod.flag("--week-start", value="<YYYY-MM-DD>", summary="Monday of the target week", required=True)

COMMAND_SCHEMA = [
    schema_mod.command("status", "Verify the Edge sidecar and SWODP API session", auth="swodp-session", flags=_COMMON + [schema_mod.flag("--json", summary="JSON output (default)")]),
    schema_mod.command("setup", "Open visible Edge and wait for interactive SWODP sign-in", auth="swodp-session", mutates=True, flags=_COMMON),
    schema_mod.command("reseed", "Silently verify and refresh the persisted browser session", auth="swodp-session", mutates=True, flags=_COMMON),
    schema_mod.command("sync", "Fetch cards and optional enrichment data", auth="swodp-session", flags=_COMMON + [_WEEK, schema_mod.flag("--range-weeks", value="<n>", summary="Weeks before/after (default: 3)"), schema_mod.flag("--cards-only", summary="Only fetch week cards")]),
    schema_mod.command("cards", "Fetch week cards in a range", auth="swodp-session", flags=_COMMON + [_WEEK, schema_mod.flag("--range-weeks", value="<n>", summary="Weeks before/after (default: 3)")]),
    schema_mod.command("history", "Fetch time-card activity history", auth="swodp-session", flags=_COMMON),
    schema_mod.command("allocations", "Fetch recent resource allocations", auth="swodp-session", flags=_COMMON + [schema_mod.flag("--since", value="<YYYY-MM-DD>", summary="Earliest allocation end date")]),
    schema_mod.command("categories", "Build the Other-category display/value map", auth="swodp-session", flags=_COMMON),
    schema_mod.command("task", "Look up a task number", auth="swodp-session", flags=_COMMON + [schema_mod.flag("<task-number>", summary="Task number", required=True), schema_mod.flag("--number", value="<task-number>", summary="Task number flag alternative")]),
    schema_mod.command("write", "Apply a validated row plan to Pending time cards", auth="swodp-session", mutates=True, destructive=True, confirmation=True, idempotent=False, flags=_COMMON + [_WEEK, schema_mod.flag("--file", value="<path|->", summary="JSON rows file or stdin", required=True), schema_mod.flag("--confirm", summary="Required outside a TTY")]),
]


def _main(argv):
    handled = schema_mod.maybe_emit_schema(argv, tool=TOOL, commands=COMMAND_SCHEMA)
    if handled is not None:
        return handled
    if not argv or argv[0] in ("help", "--help", "-h"):
        print_help()
        return 0
    if argv[0] in ("--version", "-v"):
        print(f"{TOOL} {__version__}")
        return 0
    cmd, rest = argv[0], argv[1:]
    help_result = schema_mod.maybe_emit_subcommand_help(cmd, rest, tool=TOOL, commands=COMMAND_SCHEMA)
    if help_result is not None:
        return help_result
    handlers = {
        "status": cmd_status,
        "setup": lambda values: cmd_setup(values, visible=True),
        "reseed": lambda values: cmd_setup(values, visible=False),
        "sync": cmd_sync,
        "cards": cmd_cards,
        "history": cmd_history,
        "allocations": cmd_allocations,
        "categories": cmd_categories,
        "task": cmd_task,
        "write": cmd_write,
    }
    if cmd not in handlers:
        raise UsageError(f"Unknown command: {cmd}")
    return handlers[cmd](rest)


def main(argv=None):
    return mode_mod.run_with_output_modes(
        TOOL,
        sys.argv[1:] if argv is None else argv,
        _main,
        interactive_commands=("setup",),
        fan_out_profiles=False,
    )
