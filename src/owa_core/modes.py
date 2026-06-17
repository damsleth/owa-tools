"""Shared top-level CLI modes for agent and structured-error consumers."""
import contextlib
import io
import json
import os
import sys

from .errors import OwaError, UsageError, emit_error
from .profiles_args import ALL_PROFILES, normalize_all_flags, parse_profiles
from .schema import SCHEMA_VERSION
from .version import suite_version

_TRUTHY = {'1', 'true', 'yes', 'on'}


def env_truthy(name):
    return os.environ.get(name, '').strip().lower() in _TRUTHY


def split_mode_flags(argv):
    agent = env_truthy('OWA_AGENT')
    err_json = env_truthy('OWA_ERR_JSON')
    filtered = []
    for arg in argv:
        if arg == '--agent':
            agent = True
        elif arg == '--err-json':
            err_json = True
        else:
            filtered.append(arg)
    return agent, err_json, filtered


def command_name(argv):
    for arg in argv:
        if arg == '--':
            return ''
        if not arg.startswith('-'):
            return arg
    return ''


def envelope(tool, command, data):
    meta = {
        'suite': 'owa-tools',
        'tool': tool,
        'version': suite_version(),
        'schema_version': SCHEMA_VERSION,
    }
    if command:
        meta['command'] = command
    profile = os.environ.get('OWA_PROFILE', '').strip()
    if profile:
        meta['profile'] = profile
    return {'_owa': meta, 'data': data}


def is_doctor_invocation(argv):
    """Return True only for the top-level --doctor surface.

    Command-specific arguments may legitimately contain the literal
    string ``--doctor`` as a value. Treat it as doctor mode only when
    the whole invocation is the doctor flag plus its output-mode flag.
    """
    return bool(argv) and '--doctor' in argv and all(
        arg in ('--doctor', '--json') for arg in argv
    )


@contextlib.contextmanager
def _mode_environment(tool, command, err_json):
    previous = {
        'OWA_TOOL': os.environ.get('OWA_TOOL'),
        'OWA_COMMAND': os.environ.get('OWA_COMMAND'),
        'OWA_ERR_JSON_ACTIVE': os.environ.get('OWA_ERR_JSON_ACTIVE'),
    }
    os.environ['OWA_TOOL'] = tool
    if command:
        os.environ['OWA_COMMAND'] = command
    else:
        os.environ.pop('OWA_COMMAND', None)
    if err_json:
        os.environ['OWA_ERR_JSON_ACTIVE'] = '1'
    else:
        os.environ.pop('OWA_ERR_JSON_ACTIVE', None)
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def run_with_output_modes(
    tool, argv, dispatch, *,
    binary_stdout_commands=(), interactive_commands=(), fan_out_profiles=True,
    audience=None, command_scopes=None,
):
    """Run a legacy CLI dispatcher with shared agent/error modes.

    `dispatch` receives argv with global mode flags removed and returns an
    integer exit code. In agent mode, successful JSON stdout is wrapped in a
    stable envelope for automation consumers.

    `interactive_commands` names commands that need a real terminal and emit
    no JSON (e.g. a curses TUI). They are refused under agent mode here -
    before the dispatcher authenticates or launches - so `--agent` (or
    `OWA_AGENT`) can never reach the terminal-only code path.

    `fan_out_profiles` (default True) enables multi-profile fan-out: when an
    invocation carries more than one `--profile`/`-p` value, the command runs
    once per profile and results are merged keyed by profile. With 0 or 1
    profile the original argv is passed through untouched, so behaviour is
    byte-identical to a single-profile run. Set False to opt out (the doctor
    surface does so, since `--doctor` is tool-global).

    `audience` + `command_scopes` enable scope-aware fan-out filtering on the
    `--profile all` path only. `audience` is the tool's broker audience (e.g.
    'outlook'); `command_scopes` maps a command name to the set of delegated
    scopes that grant it (any-of). When `--profile all` expands the registry,
    a profile whose token for `audience` can't be minted or carries none of
    the command's scopes is silently dropped, so a profile that structurally
    can't run the command (e.g. a DevOps-only profile with no mail scopes) no
    longer produces a permission error per profile. Explicit `--profile X`
    runs are never filtered - they still error, since naming a profile is an
    explicit request to run against it.
    """
    # Top-level --doctor surface. Intercept before
    # the legacy dispatcher so every owa-* binary picks it up via the
    # shared entry point. --json flips it to machine mode.
    if is_doctor_invocation(argv):
        from owa_core.conventions import emit_doctor
        return emit_doctor(tool, '--json' in argv)

    agent, err_json, filtered = split_mode_flags(argv)

    profiles = []
    all_requested = False
    if fan_out_profiles:
        profiles, rest = parse_profiles(normalize_all_flags(filtered))
        if ALL_PROFILES in profiles:
            all_requested = True
            try:
                profiles = _resolve_all_meta_profile(
                    profiles, tool=tool, debug=('--debug' in filtered),
                )
            except OwaError as error:
                return emit_error(
                    error, tool=tool, command=command_name(rest), err_json=err_json,
                )
    # Output shape follows intent, not count: an explicit "all" request always
    # takes the multi-profile path (profile-keyed records) even for a single
    # eligible profile, so consumers never special-case a length-1 result.
    if fan_out_profiles and (all_requested or len(profiles) > 1):
        return _run_multi_profile(
            tool, rest, profiles, dispatch,
            agent=agent, err_json=err_json,
            binary_stdout_commands=binary_stdout_commands,
            interactive_commands=interactive_commands,
            all_requested=all_requested,
            audience=audience,
            command_scopes=command_scopes,
        )

    # N<=1: byte-identical path. Pass the ORIGINAL filtered argv straight to
    # the existing code so the tool's _main and all its nuance (config-
    # subcommand --profile, OWA_PROFILE, dangling-flag errors) behave exactly
    # as before.
    command = command_name(filtered)

    if agent and command in interactive_commands:
        return emit_error(
            UsageError(
                f'{command} needs an interactive terminal and cannot run under '
                '--agent (it emits no JSON); use a scriptable command instead'
            ),
            tool=tool,
            command=command,
            err_json=err_json,
        )

    if agent and command in binary_stdout_commands and '--out' not in filtered:
        return emit_error(
            UsageError('--agent requires JSON stdout; write binary output with --out'),
            tool=tool,
            command=command,
            err_json=err_json,
        )

    with _mode_environment(tool, command, err_json):
        if not agent:
            try:
                return int(dispatch(filtered) or 0)
            except OwaError as error:
                return emit_error(error)
            except SystemExit as exc:
                return int(exc.code or 0)

        captured = io.StringIO()
        try:
            with contextlib.redirect_stdout(captured):
                rc = int(dispatch(filtered) or 0)
        except OwaError as error:
            rc = emit_error(error)
        except SystemExit as exc:
            rc = int(exc.code or 0)

        output = captured.getvalue()
        if rc != 0:
            sys.stdout.write(output)
            return rc

        text = output.strip()
        if text:
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                sys.stdout.write(output)
                return emit_error(
                    UsageError('--agent requires JSON stdout; remove --pretty or --ndjson'),
                    tool=tool,
                    command=command,
                    err_json=err_json,
                )
        else:
            data = None
        json.dump(envelope(tool, command, data), sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write('\n')
        return 0


def _resolve_all_meta_profile(profiles, *, tool, debug):
    """Expand the reserved `all` token into every eligible broker profile.

    Eligible = active (registered with the broker) AND configured. Config-less
    or inactive profiles are not part of "all". `all` is a reserved name: a real
    profile aliased `all` is a hard usage error, since it would make the
    meta-profile ambiguous. Other profile values given alongside `all` are kept,
    de-duplicated, in first-seen order.
    """
    from owa_core.auth import get_profiles

    rows = get_profiles(tool_name=tool, debug=debug)
    if any(row.alias == ALL_PROFILES for row in rows):
        raise UsageError(
            "'all' is a reserved meta-profile name; rename the profile aliased "
            "'all' in owa-piggy to use --profile all / -A / --all-profiles",
        )
    eligible = [row.alias for row in rows if row.registered and row.has_config]
    if not eligible:
        raise UsageError(
            'no active profiles to fan out across; run `owa-piggy login` first',
        )
    resolved = []
    seen = set()
    for value in profiles:
        for name in (eligible if value == ALL_PROFILES else [value]):
            if name not in seen:
                seen.add(name)
                resolved.append(name)
    return resolved


def _multi_exit_code(records):
    """0 if every profile succeeded, 1 if none did, 2 if mixed."""
    oks = [r for r in records if r['ok']]
    if len(oks) == len(records):
        return 0
    if not oks:
        return 1
    return 2


def _filter_profiles_by_scope(tool, profiles, audience, acceptable, *, debug):
    """Drop profiles whose `audience` token can't be minted or carries none
    of the `acceptable` scopes.

    Used only on the `--profile all` fan-out path: a profile that structurally
    can't run the command is silently skipped rather than failing with a
    permission error. The filter is deliberately lenient - a profile is kept
    unless it clearly can't run the command (token unmintable, or scope set
    disjoint from `acceptable`) - so a partial scope match never silently
    drops data that would have come back.

    Token scopes are advisory (read from the JWT `scp`/`roles` claims), so a
    successful mint already proves the audience is reachable; the scope
    intersection is the finer "does it carry mail/cal/... access at all" gate.
    """
    from owa_core.auth import get_token
    from owa_core.jwt import scopes_in_token

    kept = []
    for p in profiles:
        try:
            token = get_token(
                tool_name=tool, audience=audience, profile=p, debug=debug,
            )
        except OwaError:
            if debug:
                print(
                    f'DEBUG: skip profile {p!r}: cannot mint {audience} token',
                    file=sys.stderr,
                )
            continue
        if scopes_in_token(token.access_token) & acceptable:
            kept.append(p)
        elif debug:
            print(
                f'DEBUG: skip profile {p!r}: token lacks required scopes '
                f'({"/".join(sorted(acceptable))})',
                file=sys.stderr,
            )
    return kept


def _run_multi_profile(
    tool, rest, profiles, dispatch, *,
    agent, err_json, binary_stdout_commands, interactive_commands,
    all_requested=False, audience=None, command_scopes=None,
):
    """Run `dispatch` once per profile and merge the captured results.

    Each per-profile run gets exactly one well-formed `--profile <p>` appended
    so the tool's own `_main` picks it up unchanged. Output is captured per
    run and re-emitted as a single merged shape keyed by profile.
    """
    command = command_name(rest)

    if command in interactive_commands:
        return emit_error(
            UsageError(
                f'{command} needs a single interactive terminal and cannot fan '
                'out across multiple profiles; run it once per --profile'
            ),
            tool=tool,
            command=command,
            err_json=err_json,
        )
    if command in binary_stdout_commands:
        return emit_error(
            UsageError(
                f'{command} writes binary output and cannot fan out across '
                'multiple profiles; run it once per --profile'
            ),
            tool=tool,
            command=command,
            err_json=err_json,
        )

    # Scope-aware filtering: only when `all` expanded the registry (an
    # explicit --profile X is an explicit request and must still error).
    if all_requested and audience and command_scopes:
        acceptable = command_scopes.get(command)
        if acceptable:
            profiles = _filter_profiles_by_scope(
                tool, profiles, audience, acceptable,
                debug='--debug' in rest,
            )

    pretty = '--pretty' in rest
    ndjson = '--ndjson' in rest

    records = []
    for p in profiles:
        per_argv = rest + ['--profile', p]
        captured = io.StringIO()
        rc = 0
        err_msg = None
        with _mode_environment(tool, command, err_json):
            try:
                with contextlib.redirect_stdout(captured):
                    rc = int(dispatch(per_argv) or 0)
            except OwaError as error:
                rc = int(error.exit_code)
                err_msg = error.message
            except SystemExit as exc:
                rc = int(exc.code or 0)
        ok = (rc == 0 and err_msg is None)
        records.append({
            'profile': p,
            'ok': ok,
            'rc': rc,
            'output': captured.getvalue(),
            'error': err_msg,
        })

    if pretty:
        _emit_multi_pretty(records)
    elif ndjson:
        _emit_multi_ndjson(records)
    else:
        _emit_multi_json(tool, command, profiles, records)

    return _multi_exit_code(records)


def _emit_multi_json(tool, command, profiles, records):
    """Top-level merged JSON: envelope meta + per-profile results."""
    meta = {
        'suite': 'owa-tools',
        'tool': tool,
        'version': suite_version(),
        'schema_version': SCHEMA_VERSION,
    }
    if command:
        meta['command'] = command
    meta['profiles'] = profiles

    results = []
    for r in records:
        if r['ok']:
            text = r['output'].strip()
            if not text:
                data = None
            else:
                try:
                    data = json.loads(text)
                except json.JSONDecodeError:
                    results.append({
                        'profile': r['profile'],
                        'ok': False,
                        'error': 'non-JSON output',
                        'exit_code': r['rc'],
                    })
                    continue
            results.append({'profile': r['profile'], 'ok': True, 'data': data})
        else:
            results.append({
                'profile': r['profile'],
                'ok': False,
                'error': r['error'] or 'failed',
                'exit_code': r['rc'],
            })

    out = {'_owa': meta, 'results': results}
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write('\n')


def _emit_multi_pretty(records):
    """Human sections: `=== profile: p ===` then the run's verbatim output."""
    for idx, r in enumerate(records):
        if idx:
            sys.stdout.write('\n')
        if r['ok']:
            sys.stdout.write(f"=== profile: {r['profile']} ===\n")
            sys.stdout.write(r['output'])
        else:
            sys.stdout.write(f"=== profile: {r['profile']} (FAILED) ===\n")
            sys.stdout.write(f"  error: {r['error'] or 'failed'}\n")


def _emit_multi_ndjson(records):
    """One JSON object per line, each tagged with its profile."""
    for r in records:
        if not r['ok']:
            json.dump(
                {'profile': r['profile'], 'error': r['error'] or 'failed'},
                sys.stdout, ensure_ascii=False, separators=(',', ':'),
            )
            sys.stdout.write('\n')
            continue
        for line in r['output'].splitlines():
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                item = line
            json.dump(
                {'profile': r['profile'], 'item': item},
                sys.stdout, ensure_ascii=False, separators=(',', ':'),
            )
            sys.stdout.write('\n')
