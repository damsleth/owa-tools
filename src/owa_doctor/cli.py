"""Argument parsing and dispatch for `owa-doctor`.

owa-doctor is a single-shot health probe over the owa-* suite. JSON
on stdout, logs on stderr, --pretty for humans. Exit codes:
    0 - all checked profiles report 'ok'
    1 - one or more profiles in 'warn' state (near expiry)
    2 - one or more profiles in 'fail' state (or owa-piggy missing)

Invariant: a missing owa-piggy is fatal for profile checks but does
NOT prevent reporting on installed siblings - the user may run
`owa-doctor` to discover what's missing.
"""
import json
import sys

from owa_core import modes as mode_mod
from owa_core import schema as schema_mod
from owa_core.errors import UsageError, emit_message

from . import __version__
from . import probe as probe_mod
from .format import format_report_pretty


def _error(msg):
    emit_message(msg)


def _info(msg):
    print(msg, file=sys.stderr)


_PROBE_FLAGS = [
    schema_mod.flag('--profile', value='<alias>', summary='Probe only this profile (default: all profiles)'),
    schema_mod.flag('--audience', value='<name>', summary='Token audience to test (default: graph)'),
    schema_mod.flag('--no-tokens', summary='Skip per-profile token probes; only check installs'),
    schema_mod.flag('--pretty', summary='Human-readable output (default: JSON)'),
    schema_mod.flag('--debug', summary='Verbose logs to stderr (alias: --verbose)'),
]

COMMAND_SCHEMA = [
    schema_mod.command('probe', 'Run the health probe', flags=_PROBE_FLAGS),
]


def print_help():
    print("""owa-doctor - health check for the owa-* suite

Usage: owa-doctor [probe] [options]

Commands:
  probe                 Run the health probe (default command).

Probe options:
  --profile <alias>     Probe only this profile (default: all profiles
                        owa-piggy knows about).
  --audience <name>     Token audience to test (default: graph). Pass
                        outlook to verify Outlook REST is reachable.
  --no-tokens           Skip per-profile token probes; only check
                        which CLIs are installed and what version.
  --pretty              Human-readable output (default: JSON).
  --debug, --verbose    Verbose logs to stderr.
  --version             Print version and exit.
  -h, --help            Show this help.

Exit codes:
  0  all probed profiles ok
  1  one or more profiles are near expiry (< 10 min remaining)
  2  one or more profiles failed (or owa-piggy is missing)

Examples:
  owa-doctor --pretty
  owa-doctor probe --pretty
  owa-doctor --profile swon --pretty
  owa-doctor --no-tokens                # quick install check only
  owa-doctor --audience outlook --pretty""")


def _parse_args(argv):
    profile = ''
    audience = 'graph'
    no_tokens = False
    pretty = False
    debug = False
    while argv:
        a, argv = argv[0], argv[1:]
        if a == '--profile':
            if not argv:
                raise UsageError('--profile requires a value')
            profile, argv = argv[0], argv[1:]
        elif a == '--audience':
            if not argv:
                raise UsageError('--audience requires a value')
            audience, argv = argv[0], argv[1:]
        elif a == '--no-tokens':
            no_tokens = True
        elif a == '--pretty':
            pretty = True
        elif a in ('--debug', '--verbose'):
            debug = True
        else:
            raise UsageError(f'Unknown flag: {a}')
    return profile, audience, no_tokens, pretty, debug


def build_report(profile_filter='', audience='graph', no_tokens=False, debug=False):
    """Run all probes, return the structured report.

    Pure-ish: only does I/O via probe_mod (subprocess to owa-piggy).
    Tests stub probe_mod.* directly.
    """
    piggy = probe_mod.probe_piggy()
    siblings = probe_mod.probe_siblings()

    profiles_out = []
    summary = {'ok': 0, 'warn': 0, 'fail': 0}

    if no_tokens or not piggy.get('installed'):
        if not piggy.get('installed'):
            summary['fail'] = 1
        return {
            'owa_piggy': piggy,
            'siblings': siblings,
            'profiles': profiles_out,
            'summary': summary,
        }

    aliases, default = probe_mod.list_piggy_profiles()
    if profile_filter:
        if profile_filter not in aliases:
            raise UsageError(
                f"profile '{profile_filter}' not found in owa-piggy "
                f"(known: {', '.join(aliases) or 'none'})"
            )
        aliases = [profile_filter]

    for alias in aliases:
        if debug:
            _info(f'DEBUG: probing token for {alias} (audience={audience})')
        finding = probe_mod.probe_profile_token(alias, audience=audience)
        finding['default'] = (alias == default)
        finding['state'] = probe_mod.classify_finding(finding)
        summary[finding['state']] += 1
        profiles_out.append(finding)

    return {
        'owa_piggy': piggy,
        'siblings': siblings,
        'profiles': profiles_out,
        'summary': summary,
    }


def _exit_code_for(report):
    summary = report.get('summary') or {}
    if not (report.get('owa_piggy') or {}).get('installed'):
        return 2
    if summary.get('fail', 0):
        return 2
    if summary.get('warn', 0):
        return 1
    return 0


def _main(argv):
    handled = schema_mod.maybe_emit_schema(argv, tool='owa-doctor', commands=COMMAND_SCHEMA)
    if handled is not None:
        return handled

    if argv and argv[0] in ('-h', '--help', 'help'):
        print_help()
        return 0
    if argv and argv[0] == '--version':
        print(f'owa-doctor {__version__}')
        return 0
    if argv and argv[0] == 'probe':
        argv = argv[1:]
        help_rc = schema_mod.maybe_emit_subcommand_help(
            'probe', argv, tool='owa-doctor', commands=COMMAND_SCHEMA,
        )
        if help_rc is not None:
            return help_rc
    elif argv and not argv[0].startswith('-'):
        _error(f"Unknown command: {argv[0]}. Run 'owa-doctor help' for usage.")
        return 2

    profile, audience, no_tokens, pretty, debug = _parse_args(argv)
    report = build_report(
        profile_filter=profile, audience=audience,
        no_tokens=no_tokens, debug=debug,
    )

    if pretty:
        print(format_report_pretty(report))
    else:
        print(json.dumps(report))

    return _exit_code_for(report)


def main(argv=None):
    return mode_mod.run_with_output_modes(
        'owa-doctor', sys.argv[1:] if argv is None else argv, _main,
    )
