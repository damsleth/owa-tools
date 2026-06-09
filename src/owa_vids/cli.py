"""Argument parsing and dispatch for `owa-vids`.

Subcommands: info, get, check, config. A recording is addressed by one
of two sources: `--manifest-url` (the videomanifest URL copied from
DevTools) or `--embed-url` (the Teams/Stream player page URL, which
needs the cached media region).

Auth is deferred into each command handler rather than minted once in
`_main` (the suite's usual shape): the SPO token's scope is derived from
the host inside the source URL, which is known only after the command's
own flags are parsed.
"""
import json
import os
import shutil
import sys

from owa_core import modes as mode_mod
from owa_core import schema as schema_mod
from owa_core.errors import InternalError, UsageError

from . import __version__
from . import config as config_mod
from . import format as format_mod
from . import manifest as manifest_mod
from . import resolve as resolve_mod
from . import segments as segments_mod
from .http import Http


def _info(msg):
    print(msg, file=sys.stderr)


def _debug_enabled(config):
    return bool(config.get('debug')) or os.environ.get('VIDS_DEBUG') == '1'


def _require_value(flag, args):
    if not args:
        raise UsageError(f'{flag} requires a value')
    return args[0], args[1:]


def print_help():
    print("""owa-vids - download Microsoft Teams / OneDrive meeting-recap streams

Usage: owa-vids <command> [options]

Global options:
  --profile <alias>   owa-piggy profile used to mint the SharePoint token
  --debug, --verbose  Verbose HTTP / ffmpeg / auth detail (also: VIDS_DEBUG=1)
  --version           Print the suite version

Commands (unix-style verbs; suite-canonical aliases in parentheses):
  info  <source>      Probe: title, duration, resolution, tracks, segments.
                      (alias: show)   JSON by default; --pretty for a summary.
  get   <source>      Download all tracks and mux to MP4.  (alias: download)
                        --out <file>      default: the recording's own title
                        --video-only | --audio-only
                        --workdir <dir>   segment scratch (default: temp;
                                          pre-downloaded segments resume free)
  check <source>      Validate auth + manifest + first segments. (alias: probe)
  config              View / set the cached region and default profile.
                        --region <host>   e.g. switzerlandwest1-mediap.svc.ms
                        --profile <alias> pin a default owa-piggy profile

<source> (one of):
  --manifest-url '<...svc.ms/transform/videomanifest?...&format=dash>'
                      Copy from DevTools -> Network -> filter "videomanifest"
                      -> the application/dash+xml request -> Copy URL.
  --embed-url    '<...embed.aspx?uniqueId=...>'
                      The Teams/Stream player page URL. Needs the media region:
                      it's cached automatically the first time you use a
                      --manifest-url, or pass --region <host> once.

Requires ffmpeg on $PATH for `get` (the mux step).

Examples:
  owa-vids info  --manifest-url '...videomanifest...&format=dash' --profile swon --pretty
  owa-vids get   --manifest-url '...videomanifest...&format=dash' --profile swon
  owa-vids get   --embed-url 'https://...embed.aspx?uniqueId=...' --profile swon --out talk.mp4
  owa-vids config --region switzerlandwest1-mediap.svc.ms
""")
    print()
    print(schema_mod.MULTI_PROFILE_HELP)
    print()
    print(schema_mod.MACHINE_SURFACE_HELP)


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

def _parse_source(args):
    """Pull the shared source flags out of a command's args.

    Returns (manifest_url, embed_url, region_override, rest). Exactly one
    source must be present; --region is only meaningful with --embed-url
    but accepted alongside either.
    """
    manifest_url = embed_url = region = ''
    rest = []
    while args:
        flag, args = args[0], args[1:]
        if flag == '--manifest-url':
            manifest_url, args = _require_value(flag, args)
        elif flag == '--embed-url':
            embed_url, args = _require_value(flag, args)
        elif flag == '--region':
            region, args = _require_value(flag, args)
        else:
            rest.append(flag)
    if manifest_url and embed_url:
        raise UsageError('pass only one of --manifest-url / --embed-url')
    if not (manifest_url or embed_url):
        raise UsageError('need a source: --manifest-url or --embed-url')
    return manifest_url, embed_url, region, rest


def _workdir(workdir, job):
    if workdir:
        return workdir
    tag = (job.item_id or 'recap')[-12:]
    return os.path.join(os.environ.get('TMPDIR', '/tmp'), f'owa-vids-{tag}')


def _default_out(job):
    if job.title:
        return job.title if job.title.lower().endswith('.mp4') else job.title + '.mp4'
    return 'recap.mp4'


def cmd_info(args, config):
    manifest_url, embed_url, region, rest = _parse_source(args)
    pretty = False
    while rest:
        flag, rest = rest[0], rest[1:]
        if flag == '--pretty':
            pretty = True
        else:
            raise UsageError(f'Unknown flag: {flag}')

    debug = _debug_enabled(config)
    job = resolve_mod._resolve(manifest_url, embed_url, region, config, debug)
    http_client = Http(debug)
    man, _holder = manifest_mod._manifest(http_client, job, config, debug)
    v = man['tracks'].get('video', {})
    a = man['tracks'].get('audio', {})
    out = {
        'title': job.title,
        'duration_s': man['duration'],
        'width': v.get('width'), 'height': v.get('height'),
        'video_codecs': v.get('codecs'), 'audio_codecs': a.get('codecs'),
        'video_segments': len(v.get('times', [])),
        'audio_segments': len(a.get('times', [])),
        'encrypted': False,
        'region': job.region, 'driveId': job.drive_id, 'itemId': job.item_id,
    }
    if pretty:
        print(format_mod.format_info_pretty(out))
    else:
        print(json.dumps(out))
    return 0


def cmd_check(args, config):
    manifest_url, embed_url, region, rest = _parse_source(args)
    workdir = ''
    while rest:
        flag, rest = rest[0], rest[1:]
        if flag == '--workdir':
            workdir, rest = _require_value(flag, rest)
        else:
            raise UsageError(f'Unknown flag: {flag}')

    debug = _debug_enabled(config)
    job = resolve_mod._resolve(manifest_url, embed_url, region, config, debug)
    http_client = Http(debug)
    man, holder = manifest_mod._manifest(http_client, job, config, debug)
    _info(f"manifest OK - {job.title or '(untitled)'}")
    for name, tr in man['tracks'].items():
        segments_mod.download_track(http_client, name, tr, holder,
                                    _workdir(workdir, job),
                                    limit=2, probe=True, verbose=False)
        _info(f"  {name}: first segments decode OK ({len(tr['times'])} total)")
    _info('CHECK OK - auth, manifest, and segments all valid.')
    print(json.dumps({'ok': True, 'title': job.title,
                      'tracks': sorted(man['tracks'])}))
    return 0


def cmd_get(args, config):
    manifest_url, embed_url, region, rest = _parse_source(args)
    out_path = workdir = ''
    video_only = audio_only = pretty = False
    while rest:
        flag, rest = rest[0], rest[1:]
        if flag in ('--out', '-o'):
            out_path, rest = _require_value(flag, rest)
        elif flag == '--workdir':
            workdir, rest = _require_value(flag, rest)
        elif flag == '--video-only':
            video_only = True
        elif flag == '--audio-only':
            audio_only = True
        elif flag == '--pretty':
            pretty = True
        else:
            raise UsageError(f'Unknown flag: {flag}')
    if video_only and audio_only:
        raise UsageError('pass only one of --video-only / --audio-only')
    if shutil.which('ffmpeg') is None:
        raise UsageError(
            'ffmpeg not found in $PATH (needed to mux the downloaded tracks)',
            remediation='Install ffmpeg: https://ffmpeg.org/download.html',
        )

    debug = _debug_enabled(config)
    job = resolve_mod._resolve(manifest_url, embed_url, region, config, debug)
    http_client = Http(debug)
    man, holder = manifest_mod._manifest(http_client, job, config, debug)
    workdir = _workdir(workdir, job)
    wanted = ['video', 'audio']
    if video_only:
        wanted = ['video']
    if audio_only:
        wanted = ['audio']
    track_files = {}
    for name in wanted:
        if name not in man['tracks']:
            continue
        _info(f"downloading {name} ({len(man['tracks'][name]['times'])} segments)...")
        track_files[name] = segments_mod.download_track(
            http_client, name, man['tracks'][name], holder, workdir, verbose=True,
        )
    if not track_files:
        raise InternalError('manifest has no downloadable tracks')
    out_path = out_path or _default_out(job)
    _info(f'muxing -> {out_path}')
    segments_mod.mux(track_files, out_path, debug)
    result = {'out': out_path, 'bytes': os.path.getsize(out_path), 'title': job.title}
    if pretty:
        print(format_mod.format_get_pretty(result))
    else:
        print(json.dumps(result))
    return 0


def cmd_config(args, config):
    profile = region = ''
    while args:
        flag, args = args[0], args[1:]
        if flag in ('--profile', '--set-profile'):
            profile, args = _require_value(flag, args)
        elif flag == '--region':
            region, args = _require_value(flag, args)
        else:
            raise UsageError(f'Unknown flag: {flag}')

    changed = False
    if profile:
        config_mod.config_set('owa_piggy_profile', profile)
        _info(f'default profile saved: {profile}')
        changed = True
    if region:
        config_mod.config_set('region', region.strip().lower())
        _info(f'region saved: {region.strip().lower()}')
        changed = True
    if changed:
        return 0

    _info(f'Config file: {config_mod.CONFIG_PATH}')
    _info(f"  owa_piggy_profile={config.get('owa_piggy_profile') or '(not set - owa-piggy picks its default)'}")
    _info(f"  region={config.get('region') or '(not set - learned from --manifest-url)'}")
    return 0


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

AUTHED_COMMANDS = {'info', 'get', 'check'}

_SOURCE_FLAGS = [
    schema_mod.flag('--manifest-url', value='<url>',
                    summary='videomanifest URL copied from DevTools (...&format=dash)'),
    schema_mod.flag('--embed-url', value='<url>',
                    summary='Teams/Stream player page URL (needs cached or explicit --region)'),
    schema_mod.flag('--region', value='<host>',
                    summary='Media region host for --embed-url, e.g. switzerlandwest1-mediap.svc.ms'),
]

_INFO_FLAGS = _SOURCE_FLAGS + [
    schema_mod.flag('--pretty', summary='Human-readable summary (default: JSON)'),
]

_GET_FLAGS = _SOURCE_FLAGS + [
    schema_mod.flag('--out', value='<file>',
                    summary="Output MP4 path (default: the recording's own title)"),
    schema_mod.flag('-o', value='<file>', summary='Short for --out'),
    schema_mod.flag('--workdir', value='<dir>',
                    summary='Segment scratch dir (default: temp; enables resume)'),
    schema_mod.flag('--video-only', summary='Download only the video track'),
    schema_mod.flag('--audio-only', summary='Download only the audio track'),
    schema_mod.flag('--pretty', summary='Human one-liner instead of the JSON result'),
]

_CHECK_FLAGS = _SOURCE_FLAGS + [
    schema_mod.flag('--workdir', value='<dir>',
                    summary='Segment scratch dir (default: temp)'),
]

_CONFIG_FLAGS = [
    schema_mod.flag('--profile', value='<alias>',
                    summary='Pin a default owa-piggy profile alias (owa_piggy_profile)'),
    schema_mod.flag('--set-profile', value='<alias>', summary='Alias for --profile'),
    schema_mod.flag('--region', value='<host>', summary='Pin the media region host'),
]

COMMAND_SCHEMA = [
    schema_mod.command(
        'info', 'Probe a recording: title, duration, resolution, tracks, segments',
        auth='graph', flags=_INFO_FLAGS, aliases=['show'],
    ),
    schema_mod.command(
        'get', 'Download all tracks and mux to MP4 (local file; no remote writes)',
        auth='graph', flags=_GET_FLAGS, aliases=['download'],
    ),
    schema_mod.command(
        'check', 'Validate auth, manifest, and first segments without a full download',
        auth='graph', flags=_CHECK_FLAGS, aliases=['probe'],
    ),
    schema_mod.command(
        'config', 'View or update configuration', mutates=True, flags=_CONFIG_FLAGS,
    ),
]


def _command_name(argv):
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ('--debug', '--verbose'):
            i += 1
            continue
        if a == '--profile':
            i += 2
            continue
        return a
    return ''


def _main(argv):
    handled = schema_mod.maybe_emit_schema(argv, tool='owa-vids', commands=COMMAND_SCHEMA)
    if handled is not None:
        return handled

    if not argv:
        print_help()
        return 0
    if argv[0] in ('help', '--help', '-h'):
        print_help()
        return 0
    if argv[0] in ('--version', '-v'):
        print(f'owa-vids {__version__}')
        return 0

    debug_flag = False
    profile_override = ''
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
    # info/get/check are the primary verbs; show/download/probe are accepted
    # as suite-canonical aliases (resolved before help and dispatch).
    cmd = schema_mod.resolve_alias(cmd, COMMAND_SCHEMA)

    help_rc = schema_mod.maybe_emit_subcommand_help(
        cmd, rest, tool='owa-vids', commands=COMMAND_SCHEMA,
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

    if cmd not in AUTHED_COMMANDS:
        raise UsageError(f"Unknown command: {cmd}. Run 'owa-vids help' for usage.")

    schema_mod.precheck_required_args(cmd, rest, commands=COMMAND_SCHEMA)

    # Auth is deferred into each handler: the SPO token's scope depends on
    # the host inside the source URL, parsed by the handler's own flags.
    if cmd == 'info':
        return cmd_info(rest, config)
    if cmd == 'check':
        return cmd_check(rest, config)
    if cmd == 'get':
        return cmd_get(rest, config)

    return 1


def main(argv=None):
    return mode_mod.run_with_output_modes(
        'owa-vids',
        sys.argv[1:] if argv is None else argv,
        _main,
        # `get` writes the MP4 to disk and prints a JSON result line - not
        # bytes - so it is NOT a binary stdout command. Revisit only if a
        # future `--out -` pipe mode is added.
        binary_stdout_commands=(),
    )
