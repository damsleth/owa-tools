# owa-vids merge into owa-tools

> **Status: SHIPPED** — landed in **v0.8.0** (`d2f5502`, 2026-06-03,
> `feat(owa-vids): add meeting-recap video downloader as 13th binary`),
> released 2026-06-05. All twelve steps complete: package, registry, docs,
> completions, contract tests, `src/tests/vids/` (63 tests),
> and the Homebrew tap bump. See [../DONE.md](../DONE.md).

_Created 2026-06-03_

Merge the standalone `owa-vids` script into the owa-tools monorepo as a first-class package `src/owa_vids/`, shipped as the 13th binary (`owa-vids`). The package downloads Microsoft Teams / OneDrive meeting-recap DASH streams using token-only auth (no browser cookies, no decryption) and muxes them to MP4 via ffmpeg.

## Goal

- Deliver `owa-vids` as `src/owa_vids/` inside the monorepo, registered in every hardcoded list in the suite.
- Refactor auth, config, errors, and HTTP onto `owa_core` primitives (`owa_core.auth`, `owa_core.config`, `owa_core.http`, `owa_core.errors`, `owa_core.modes`). Retain novel domain code (manifest parsing, DASH timeline expansion, segment loop, SPO identity resolution) verbatim from `owa-vids`.
- Bump the Homebrew tap formula.
- **ZERO new third-party runtime dependencies** — confirmed below; no resolution needed.

## Current state (from survey)

### owa-vids (standalone script)

The entire tool is a single file `owa-vids` (677 lines). No package structure. No `setup.py` / `pyproject.toml`. Runs as a raw Python script. Key domains:

- `owa-vids:1–65` — module constants: `VERSION = "0.1.0"`, `UA`, `TRANSIENT = {408,429,500,502,503,504}`, `DELAY = 0.10`, `CONFIG_PATH = ~/.config/owa-vids/config.json`, exit codes `EXIT_USAGE=2`/`EXIT_AUTH=12`.
- `owa-vids:69–90` — `info(msg)` (stderr), `die(msg, code)` (stderr + `sys.exit`), `load_config()` / `save_config(cfg)` reading a JSON dict (NOT the `KEY="VALUE"` shell format used by owa-tools).
- `owa-vids:95–119` — `mint_token(profile, *, scope, audience, debug)`: shells out to `owa-piggy token --audience <a> --json`, parses `.access_token`. Direct reimplementation of `owa_core.auth.get_token_for_config` (`src/owa_core/auth.py:163`). **Must be replaced** by the core primitive.
- `owa-vids:125–177` — `class Http`: per-host `http.client.HTTPSConnection` with keep-alive recycling, `TRANSIENT` backoff, `Retry-After` on 429, exponential backoff on connection errors. **This is NOT equivalent to `owa_core.http.request`** (`src/owa_core/http.py:104`), which uses `urllib.request.urlopen` and does not maintain per-host connections. The keep-alive strategy is load-bearing for svc.ms throttle compliance — **keep as `owa_vids/http.py`**.
- `owa-vids:180–184` — `graph_get(http, token, url)`: thin wrapper; equivalent in shape to `owa_core.http.request` (`src/owa_core/http.py:104`) but uses the local `Http` class. Keep in `owa_vids/http.py` alongside the `Http` class.
- `owa-vids:191–200` — `class Job`: dataclass-like plain class. Novel. No analog in any `owa_core` or `owa_drive` module.
- `owa-vids:203–294` — `resolve_manifest_url`, `_docid_base`, `_attach_drive_item`, `_fetch_title`, `resolve_embed_url`, `graph_get_spo`. The embed-URL path uses `__import__("base64").urlsafe_b64encode` (owa-vids:271) — stdlib only.
- `owa-vids:300–402` — `build_manifest_url`, `fetch_manifest`, `_parse_iso_duration`, `_expand_timeline`, `parse_manifest`, `_intattr`, `_with_token`. `_parse_iso_duration` (`owa-vids:322–334`) and `_expand_timeline` (`owa-vids:337–363`) carry the two bug fixes from commit `2cae29f` (ISO-8601 full-form duration, `r="-1"` open-ended timeline).
- `owa-vids:408–459` — `download_track` (segment loop with `.part`-file atomicity, progress every 20 segs, 0.10s `DELAY`) and `_get_segment` (auth-retry `token_holder` dict, single refresh on 401/403, also from `2cae29f`).
- `owa-vids:462–471` — `mux`: `ffmpeg -y -loglevel error -i video.m4s -i audio.m4s -c copy <out>` via `subprocess.run(check=True)`.
- `owa-vids:476–583` — `_resolve`, `_manifest`, `cmd_info`, `cmd_check`, `cmd_get`, `cmd_config`, `_workdir`, `_default_out`.
- `owa-vids:589–677` — `ALIASES = {"download": "get", "show": "info", "probe": "check"}`, `HELP`, `build_parser()` (argparse), `main()`.

### Crypto dependency audit: **CLEAN — zero action required**

`owa-vids` deliberately avoids encryption by omitting `enableEncryption` from the manifest URL (`owa-vids:12–19`). `parse_manifest` calls `die()` at `owa-vids:368` if `ContentProtection`/`sea:` appears. No imports of `cryptography`, `pycryptodome`, `Crypto`, `hashlib` for key material, nor any subprocess to `openssl` or ffmpeg decryption flags. The only `hashlib`-adjacent operation is `base64.urlsafe_b64encode` at `owa-vids:271` — stdlib, zero dep. The AES-128-CBC path (SEA, `VideoProtectionKey`) lives exclusively in `recap-dl.py` which is **dropped**. The **owa-tools zero-third-party-dep contract is fully met**.

### owa_core hooks available

- `src/owa_core/auth.py:163` — `get_token_for_config(config, *, tool_name, audience, scope, debug)` returns `BrokerToken`; `.access_token` is the string. Replaces `owa-vids:mint_token` for the initial Graph and SPO tokens.
- `src/owa_core/auth.py:109` — `get_token(*, tool_name, audience, profile, scope, debug)` for direct profile-aware calls; not needed if config carries the profile.
- `src/owa_core/config.py:37` — `load_config_file(path)` reads `KEY="VALUE"` lines (NOT JSON). **Config format must change** from `owa-vids`'s `config.json` to the suite-standard shell-sourceable format.
- `src/owa_core/config.py:46,91` — `save_config(path, config)` and `config_set(path, allowed_keys, key, value)`.
- `src/owa_core/errors.py:15,27` — `ExitCode` enum, `UsageError`, `AuthExpiredError`, `ScopeInsufficientError`, `InternalError`, `NetworkError`. Replace `EXIT_USAGE=2`/`EXIT_AUTH=12` constants and `die()`.
- `src/owa_core/errors.py:87` — `emit_error(error, *, stream, tool, command, err_json)`.
- `src/owa_core/modes.py:96` — `run_with_output_modes('owa-vids', argv, _main, binary_stdout_commands=('get',))`.
- `src/owa_core/schema.py:45,68,154,322,258,104` — `flag`, `command`, `maybe_emit_schema`, `maybe_emit_subcommand_help`, `precheck_required_args`, `resolve_alias`.
- `src/owa_core/schema.py:17,29` — `MACHINE_SURFACE_HELP`, `MULTI_PROFILE_HELP` — append verbatim at end of `print_help()`.
- `src/owa_core/registry.py:31` — `CONSUMER_TOOLS` tuple; append `"owa-vids"` after `"owa-teams"`.
- `src/owa_core/version.py:44` — `binary_version('owa-vids')` replaces the hardcoded `VERSION = "0.1.0"`.
- `src/owa_core/format.py:4,12,23,28` — `pad`, `truncate`, `date_part`, `time_part` for `--pretty` tables.
- `src/owa_core/http.py:104` — `request` and `request_unauthenticated` available but **not used** for svc.ms segment fetches (keep-alive constraint; see Design Decision 3).

### Existing suite state

> Anchors below verified against the working tree on 2026-06-03: `src/owa_core/registry.py:31` ends `CONSUMER_TOOLS` at `"owa-teams"`; `pyproject.toml:43` is the last console script (`owa-teams`), `:62` the last package, `:95` the last coverage source. Other line numbers are from the survey — re-confirm at edit time.

- `src/owa_core/registry.py:20–32` — `CONSUMER_TOOLS` has 11 entries ending at `"owa-teams"` (line 31).
- `pyproject.toml:43` — last console script is `owa-teams = "owa_teams:main"`.
- `pyproject.toml:62` — last package in `[tool.setuptools]packages` is `"owa_teams"`.
- `pyproject.toml:95` — last coverage source is `"owa_teams"`.
- `README.md:41` — reads `"twelve binaries"`.
- `AGENTS.md:8` — reads `"eleven console scripts"` (stale; does not yet include owa-planner/owa-sites/owa-teams).
- `src/tests/contract/test_suite_contract.py:6–17` — `TOOLS` tuple has 11 entries ending at `"owa_teams"`.
- `src/tests/contract/test_multi_profile_fanout.py:22–30` — `FANNING_TOOLS` has 9 entries; missing `owa_teams`.
- `src/tests/test_architecture_contracts.py:7–18` — `RUNTIME_DIRS` has 10 entries ending at `"owa_todo"` (missing `owa_planner`, `owa_sites`, `owa_teams`).
- `src/tests/test_agents_index.py:8–27` — `INDEXED_PATHS` has no `src/owa_vids/AGENTS.md`; `RUNTIME_PACKAGES:29–40` has 10 entries ending at `"owa_todo"` (stale).
- `src/scripts/check_stdlib_only.py:39–53` — `LOCAL_PACKAGES` frozenset has 12 entries ending at `"owa_sites"` (missing `owa_teams`).
- `src/scripts/check_console_smoke.py:15–25` — `TOOLS` has 10 entries ending at `"owa-sites"` (missing `owa-teams`).
- `src/scripts/check_docs_sync.py:27–38` — `DOCS` dict has 11 entries ending at `'owa-teams'`.
- `src/completions/` — only `owa-graph.{bash,zsh,fish}` exist; no per-tool completions for newer packages.
- `~/code/homebrew-tap/Formula/owa-tools.rb:21` — binary test list has 12 entries; `owa-vids` absent.

## Design decisions

1. **Module layout mirrors `owa_drive`** (`src/owa_drive/`): `__init__.py`, `__main__.py`, `cli.py`, `api.py`, `auth.py`, `config.py`, `format.py`, `http.py` (novel), `resolve.py` (novel), `manifest.py` (novel), `segments.py` (novel), `AGENTS.md`. The domain is larger than drive's but the structure is identical at the public-surface level.

2. **Config format migrates from JSON to `KEY="VALUE"`**. `owa-vids` stores `~/.config/owa-vids/config.json` with keys `region` and `profile`. The suite standard is `KEY="VALUE"` shell-sourceable format managed by `owa_core.config`. Migration: `config.py` declares `CONFIG_PATH = ~/.config/owa-vids/config` (no `.json`), `ALLOWED_KEYS = ('owa_piggy_profile', 'debug', 'region')`. The `region` key is novel to this tool and must be in `ALLOWED_KEYS`. Note that the `owa-vids` config key is `profile` but the suite convention is `owa_piggy_profile`; migration maps the old key at load time (one-time migration helper in `config.py`).

3. **`owa_vids/http.py` keeps the custom `Http` class** (from `owa-vids:125–177`). `owa_core.http.request` uses `urllib.request.urlopen` which does not maintain per-host persistent connections. The svc.ms CDN throttles reconnects aggressively; the keep-alive strategy is empirically required. `Http` and `graph_get` stay as a self-contained local module. No `urllib.request` is imported in `owa_vids/http.py` — only `http.client.HTTPSConnection`. This is the single justified exception to delegating all HTTP to `owa_core`.

4. **Auth uses `owa_core.auth.get_token_for_config` for initial minting; re-minting inside the segment loop calls it directly via a closure**. `owa-vids`'s `token_holder["refresh"]` lambda (`owa-vids:487`) must call `owa_core.auth.get_token(tool_name='owa-vids', audience='spo', profile=..., scope=..., debug=...)` (`src/owa_core/auth.py:109`), not shell out to owa-piggy manually. The lambda cannot use `get_token_for_config` because it operates outside the normal config-load cycle; `get_token` is the right primitive here.

5. **`get` is NOT a `binary_stdout_command`.** `cmd_get` writes the downloaded file to disk and emits `json.dumps({"out", "bytes", "title"})` metadata to stdout — JSON, not bytes. So `binary_stdout_commands=()`. Only add `'get'` to that tuple if a future `--out -` (pipe-to-stdout) mode is implemented.

6. **`--pretty` follows the suite convention**: pretty output goes to stdout (not stderr as in `owa-vids`). `cmd_info` currently sends the human summary to `info()` (stderr). In the monorepo version, `--pretty` prints to stdout; the raw JSON is the default. This is a deliberate behaviour change to match every other tool's `--pretty` contract (`src/owa_drive/cli.py:144–145`).

7. **Download-bypass caveat**: `docs/vids.md` includes one honest sentence: "The `get` command fetches the DASH manifest without the `enableEncryption` parameter, which causes the service to return clear (unencrypted) segments. This is a property of the service, not a crack. Use only for recordings you have legitimate access to." Approved by the repo owner — present but not headlined.

8. **`cmd_config` exposes `--region` as a positional write** (`config --region <host>`) and `owa_piggy_profile` via the suite-standard `config set owa_piggy_profile <alias>` pattern (matching `owa_drive/cli.py` config verb). The old `--set-profile` flag maps to `config set owa_piggy_profile`.

9. **No `recap-dl.py`**. The AES-CBC encrypted path (SEA, `VideoProtectionKey`, PKCS#7 padding, constant IV) is dropped entirely. `parse_manifest` at `owa-vids:368` already calls `die()` on encrypted manifests — this check is kept and converted to a `raise UsageError(...)`.

## Implementation plan

### Step 1 — Create `src/owa_vids/` package skeleton

**New files** (all under `/Users/damsleth/code/owa-tools/src/owa_vids/`):

- `__init__.py`: expose `main` and `__version__ = suite_version()` (mirror `src/owa_drive/__init__.py:1–6`).
- `__main__.py`: `import sys; from .cli import main; sys.exit(main())` (mirror `src/owa_drive/__main__.py`).
- `config.py`: `CONFIG_PATH`, `ALLOWED_KEYS = ('owa_piggy_profile', 'debug', 'region')`, thin wrappers. One-time migration helper `_migrate_json_config()` reads old `.json` file if it exists, writes in `KEY="VALUE"` format, then deletes the old file. Called at the top of `load_config()`.
- `auth.py`: `TOOL_NAME = 'owa-vids'`. The initial token for manifest access is an SPO-scoped token; the Graph token for `_fetch_title` is minted separately. `API_BASE` is not a single constant here — the svc.ms host is dynamic (see Risk 4). `setup_auth(config, spo_host, debug)` calls `owa_core.auth.get_token_for_config(config, tool_name=TOOL_NAME, audience='graph', debug=debug)` for the initial Graph token and `get_token_for_config(config, ..., audience='spo', scope=f'https://{spo_host}/.default')` for the SPO token. Returns `(graph_token, spo_token)` or a namedtuple. `make_spo_refresh(config, spo_host, debug)` returns the lambda used in `token_holder["refresh"]`, calling `owa_core.auth.get_token(tool_name=TOOL_NAME, audience='spo', profile=..., scope=..., debug=debug)` directly.
- `http.py`: the `Http` class (`owa-vids:125–177`) and `graph_get` (`owa-vids:180–184`), translated from `die()` to `raise NetworkError(...)` / `raise AuthExpiredError(...)`. Import `from owa_core.errors import NetworkError, AuthExpiredError`. Import `http.client`, `time`, `urllib.parse.urlsplit` — all stdlib.
- `resolve.py`: `Job` class (`owa-vids:191–200`), `resolve_manifest_url` (`owa-vids:209–226`), `_docid_base` (`owa-vids:203–206`), `_attach_drive_item` (`owa-vids:229–232`), `_fetch_title` (`owa-vids:235–246`), `resolve_embed_url` (`owa-vids:249–283`), `graph_get_spo` (`owa-vids:286–294`). Config writes in `resolve_manifest_url` call `config_mod.config_set` rather than the old `save_config(cfg)`. `die(...)` calls become `raise UsageError(...)` or `raise NotFoundError(...)`.
- `manifest.py`: `build_manifest_url` (`owa-vids:300–310`), `fetch_manifest` (`owa-vids:313–319`), `_parse_iso_duration` (`owa-vids:322–334`), `_expand_timeline` (`owa-vids:337–363`), `parse_manifest` (`owa-vids:366–390`), `_intattr` (`owa-vids:393–395`), `_with_token` (`owa-vids:398–402`). `die(...)` on encrypted manifest becomes `raise UsageError('manifest came back encrypted; this build expects the clear path')`. `die(...)` on open-ended timeline without duration becomes `raise InternalError(...)`.
- `segments.py`: `download_track` (`owa-vids:408–438`), `_get_segment` (`owa-vids:441–459`), `mux` (`owa-vids:462–471`). `die()` calls become typed `OwaError` subclasses. The `DELAY = 0.10` constant moves here (or to a `constants.py` if preferred). `_get_segment`'s `token_holder["refresh"]` lambda is supplied from `auth.make_spo_refresh(...)`.
- `format.py`: `format_info_pretty(out_dict)`, `format_check_pretty(job, tracks)`, `format_get_pretty(result)` — rendering for `--pretty`. Use `owa_core.format.pad` and `owa_core.format.truncate` (`src/owa_core/format.py:4,12`). No ANSI, no third-party libs.
- `cli.py`: `COMMAND_SCHEMA`, `print_help()`, `_main(argv)`, `main(argv=None)`. Detail below.
- `AGENTS.md`: follow `src/owa_drive/AGENTS.md` pattern exactly.

### Step 2 — Write `cli.py` in full

`cli.py` owns argument parsing and dispatch. Follow `src/owa_drive/cli.py:1–644` structure exactly.

**Imports** (mirrors `src/owa_drive/cli.py:11–34`):

```python
import json, os, sys
from owa_core import modes as mode_mod, schema as schema_mod
from owa_core.errors import UsageError, AuthExpiredError, OwaError, emit_error, emit_message
from . import __version__
from . import auth as auth_mod, config as config_mod, format as format_mod
from . import manifest as manifest_mod, resolve as resolve_mod, segments as segments_mod
from .http import Http
```

**Helpers** (mirrors `src/owa_drive/cli.py:37–52`):

```python
def _error(msg):   emit_message(msg)
def _info(msg):    print(msg, file=sys.stderr)
def _debug_enabled(config): return bool(config.get('debug')) or os.environ.get('VIDS_DEBUG') == '1'
```

**`print_help()`**: adapted from `owa-vids:591–626` docstring. Appends `schema_mod.MULTI_PROFILE_HELP` and `schema_mod.MACHINE_SURFACE_HELP` at the end (mirrors `src/owa_drive/cli.py:108–110`).

**Commands**:

```python
COMMAND_SCHEMA = [
    schema_mod.command('info',   'Probe: title, duration, resolution, tracks, segments.',
                       auth='spo', aliases=['show']),
    schema_mod.command('get',    'Download and mux to MP4.',
                       auth='spo', aliases=['download']),
    schema_mod.command('check',  'Validate auth, manifest, and first segments.',
                       auth='spo', aliases=['probe']),
    schema_mod.command('config', 'View or set cached region and default profile.',
                       auth=None),
]
```

**`_main(argv)` dispatch order** (mirrors `src/owa_drive/cli.py:552–635`):

1. `schema_mod.maybe_emit_schema(argv, tool='owa-vids', commands=COMMAND_SCHEMA)` — first.
2. Strip `--debug`/`--profile`/`--region` globals into local vars.
3. `cmd = schema_mod.resolve_alias(cmd, COMMAND_SCHEMA)`.
4. `schema_mod.maybe_emit_subcommand_help(cmd, rest, ...)`.
5. `config = config_mod.load_config()`, apply debug/profile overrides.
6. `cmd_config` runs unauthenticated.
7. `schema_mod.precheck_required_args(cmd, rest, commands=COMMAND_SCHEMA)`.
8. Auth is deferred into each `cmd_*` function (see note below), because `setup_auth` needs the SPO host extracted from the source URL.
9. Dispatch to `cmd_info`, `cmd_check`, `cmd_get`.

**`main(argv=None)`**:

```python
def main(argv=None):
    return mode_mod.run_with_output_modes(
        'owa-vids',
        sys.argv[1:] if argv is None else argv,
        _main,
        binary_stdout_commands=(),   # get outputs JSON metadata, not bytes
        interactive_commands=(),
    )
```

**Command implementations** (translate `owa-vids:491–570`):

- `cmd_info`: parse `--pretty`, `--manifest-url`/`--embed-url`/`--region`. Call `resolve_mod._resolve(...)`, `manifest_mod._manifest(...)`. Build output dict. `--pretty` → `format_mod.format_info_pretty(out)` to stdout; else `print(json.dumps(out))`.
- `cmd_get`: parse `--out`, `--workdir`, `--video-only`, `--audio-only`. On completion: `print(json.dumps({"out": out_path, "bytes": size, "title": job.title}))`. Uses `action_envelope`/`emit_action` from `src/owa_core/conventions.py:80,102` for the mutation result shape.
- `cmd_check`: stderr progress via `_info()`; returns 0 on success, raises `InternalError` on probe failure.
- `cmd_config`: handles `set owa_piggy_profile <alias>` (suite pattern) and the legacy `--set-profile` alias.

**Note on deferred auth**: Because `setup_auth` needs the SPO host extracted from the source URL, and that host is known only after parsing the command's own flags, auth is deferred into each `cmd_*` function rather than in `_main`. This is a deliberate deviation from `owa_drive`'s pattern. `_main` still calls `schema_mod.precheck_required_args` before dispatch, but does not call `auth_mod.setup_auth` at the top level.

### Step 3 — Register in `pyproject.toml`

Edit `/Users/damsleth/code/owa-tools/pyproject.toml`:

- After `owa-teams = "owa_teams:main"` (line 43): add `owa-vids = "owa_vids:main"`.
- In `[tool.setuptools]packages` after `"owa_teams"` (line 62): add `"owa_vids"`.
- In `[tool.coverage.run]source` after `"owa_teams"` (line 95): add `"owa_vids"`.

### Step 4 — Register in `owa_core` registry and suite scripts

**`src/owa_core/registry.py:31`**: append `"owa-vids",` after `"owa-teams"`. This single edit propagates to `owa list`, `owa schema`, and `owa-doctor`'s `SIBLINGS` probe automatically.

**`src/scripts/check_stdlib_only.py`**: add `"owa_vids"` to `LOCAL_PACKAGES` frozenset (after `"owa_sites"` at line ~51). Also add the currently missing `"owa_teams"` while touching the file.

**`src/scripts/check_console_smoke.py`**: add `'owa-vids'` to `TOOLS` tuple (line ~25). Also add the missing `'owa-teams'`.

**`src/scripts/check_docs_sync.py`**: add import `from owa_vids.cli import COMMAND_SCHEMA as VIDS_SCHEMA` after line 24; add `'owa-vids': ('docs/vids.md', VIDS_SCHEMA),` to `DOCS` dict.

### Step 5 — Update contract and architecture tests

**`src/tests/contract/test_suite_contract.py:6–17`**: add `"owa_vids",` to `TOOLS` tuple.

**`src/tests/contract/test_multi_profile_fanout.py:22–30`**: add `("owa_vids", ["info", "--manifest-url", "https://example-mediap.svc.ms/transform/videomanifest?docid=x&format=dash"]),` to `FANNING_TOOLS`. Also add the missing `("owa_teams", ["teams"])` entry.

**`src/tests/test_architecture_contracts.py:7–18`**: add `"owa_vids"` to `RUNTIME_DIRS`. Also add the missing `"owa_planner"`, `"owa_sites"`, `"owa_teams"`.

**`src/tests/test_agents_index.py:8–27`**: add `'src/owa_vids/AGENTS.md'` to `INDEXED_PATHS`. In `RUNTIME_PACKAGES:29–40`: add `'owa_planner'`, `'owa_sites'`, `'owa_teams'`, `'owa_vids'`.

### Step 6 — Write `docs/vids.md`

Required by `check_docs_sync.py` (every tool in `DOCS` must have a doc file). Content: tool purpose, the four commands (`info`, `get`, `check`, `config`) with their flags, examples for both `--manifest-url` and `--embed-url`, the `--profile` and `--debug` globals, the download-bypass caveat sentence (see Design Decision 7), and a note on ffmpeg as a runtime dependency.

Example commands block in docs:

```bash
# Probe a recording
owa-vids info --manifest-url 'https://swon-mediap.svc.ms/transform/videomanifest?docid=...&format=dash' --profile swon --pretty

# Download and mux
owa-vids get --manifest-url 'https://swon-mediap.svc.ms/...' --profile swon -o meeting.mp4

# Embed-URL path (region must already be cached or --region passed)
owa-vids get --embed-url 'https://tenant.sharepoint.com/personal/user/_layouts/15/embed.aspx?uniqueId=...' --profile swon

# Cache the region
owa-vids config --region switzerlandwest1-mediap.svc.ms
```

### Step 7 — Write `src/owa_vids/AGENTS.md`

```markdown
# AGENTS.md

`owa_vids` downloads Microsoft Teams / OneDrive meeting-recap video streams.

- Auth audience is `spo` (SPO-scoped token for the svc.ms manifest) plus
  `graph` (for identity resolution and title fetch).
- The segment download loop (`segments.py:download_track`) uses
  `owa_vids.http.Http` (persistent keep-alive) rather than `owa_core.http` —
  this is intentional; do not refactor to `owa_core.http` without re-testing
  against a live svc.ms tenant.
- No writes to SharePoint. All operations are read-only (GET + ffmpeg mux
  to a local file). No `--confirm` machinery needed.
- `recap-dl.py` (AES-CBC decryption fallback) is explicitly NOT part of this
  package. Do not add decryption.
- Docs live in `docs/vids.md`.
- Nearest tests: `src/tests/vids/`.

Verify:

    .venv/bin/ruff check src/owa_vids src/tests/vids
    .venv/bin/python -m pytest -q src/tests/vids
```

### Step 8 — Update `README.md`, `AGENTS.md`, `CHANGELOG.md`

**`README.md:41`**: `"twelve binaries"` → `"thirteen binaries"`. Update the binary list on line 43 to include `owa-vids`. Add a row to the "What's in the box" table for `owa-vids`: `` | `owa-vids` | Download Teams / OneDrive meeting-recap DASH streams and mux to MP4. | ``. Add `vids` to the per-tool doc links.

**`AGENTS.md:8`**: update suite description count. Current reads `"eleven console scripts"` (stale). Update to `"thirteen console scripts"` and list all 13. Add `` | `src/owa_vids/AGENTS.md` | `` row to the Repository Map table after `src/owa_teams/AGENTS.md`.

**`CHANGELOG.md:9`**: add `### owa-vids (new)` subsection under `## Unreleased`. Include: token-only DASH download pipeline, `info`/`get`/`check`/`config` verbs, `--manifest-url` and `--embed-url` sources, ffmpeg mux, no third-party deps.

### Step 9 — Shell completions

Create three new files following `src/completions/owa-graph.{bash,zsh,fish}` patterns:

- `src/completions/owa-vids.bash`
- `src/completions/owa-vids.zsh`
- `src/completions/owa-vids.fish`

Commands to complete: `info get check config` plus their aliases (`show download probe`). Global flags: `--profile`, `--debug`, `--version`, `--help`. Command-specific: `--manifest-url`, `--embed-url`, `--region`, `--out`, `--workdir`, `--video-only`, `--audio-only`, `--pretty`, `--set-profile`.

### Step 10 — Update Homebrew tap

After a PyPI release, edit `~/code/homebrew-tap/Formula/owa-tools.rb`:

- Line 6: update `url` tag to new version.
- Line 7: bump `version`.
- Line 8: update `sha256`.
- Line 4: optionally update `desc` to mention video streams.
- Line 21: change `%w[owa owa-cal ...]` to include `owa-vids` after `owa-teams`.
- Update the comment `"All twelve binaries"` to `"All thirteen binaries"`.

### Step 12 — Write `src/tests/vids/`

See Tests section below.

## Tests

### Contract tests that must be updated (enumeration of all binaries)

All of the following require manual edits to add `"owa_vids"` (and fix pre-existing staleness where noted):

| File | Location | Edit |
|---|---|---|
| `src/tests/contract/test_suite_contract.py` | `TOOLS:6–17` | add `"owa_vids"` |
| `src/tests/contract/test_multi_profile_fanout.py` | `FANNING_TOOLS:22–30` | add `owa_vids` + missing `owa_teams` |
| `src/tests/test_architecture_contracts.py` | `RUNTIME_DIRS:7–18` | add `owa_vids` + stale `owa_planner`/`owa_sites`/`owa_teams` |
| `src/tests/test_agents_index.py` | `INDEXED_PATHS:8–27`, `RUNTIME_PACKAGES:29–40` | add `src/owa_vids/AGENTS.md` and `owa_vids`; fix stale entries |
| `src/scripts/check_docs_sync.py` | `DOCS` dict | add `owa-vids` import + entry |
| `src/scripts/check_console_smoke.py` | `TOOLS:15–25` | add `owa-vids` + missing `owa-teams` |
| `src/scripts/check_stdlib_only.py` | `LOCAL_PACKAGES:39–53` | add `owa_vids` + stale `owa_teams` |
| `src/owa_core/registry.py` | `CONSUMER_TOOLS:20–32` | add `"owa-vids"` |
| `pyproject.toml` | scripts, packages, coverage | three additions |

`src/tests/contract/test_doctor_flag.py` derives `_BINARIES` from `owa_core.registry.CONSUMER_TOOLS` at import time — **automatically covers `owa-vids` once registry is updated** (no manual edit needed).

### New test set: `src/tests/vids/`

**`__init__.py`**: empty.

**`conftest.py`**:
```python
import pytest

@pytest.fixture
def tmp_config(tmp_path, monkeypatch):
    from owa_vids import config as config_mod
    fake = tmp_path / 'owa-vids' / 'config'
    monkeypatch.setattr(config_mod, 'CONFIG_PATH', fake)
    return fake

@pytest.fixture
def clean_env(monkeypatch):
    for key in ('OWA_PROFILE', 'VIDS_DEBUG', 'XDG_CONFIG_HOME'):
        monkeypatch.delenv(key, raising=False)
```

**`test_cli_smoke.py`** (subprocess black-box, no mocks):
- `test_no_args_shows_help` — `python -m owa_vids` → rc 0, `"owa-vids"` in stdout.
- `test_help_flag` — `--help` → rc 0.
- `test_version_flag` — `--version` → rc 0, `"owa-vids "` prefix in stdout.
- `test_schema_subcommand` — `schema` → rc 0, JSON with `tool == "owa-vids"`.
- `test_unknown_command_exits_2` — `frobnicate` → rc 2, no traceback in stderr.
- `test_get_without_source_exits_2` — `get` with no `--manifest-url`/`--embed-url` → rc 2.

**`test_auth.py`** (mirrors `src/tests/drive/test_auth.py`):
- `test_setup_auth_calls_piggy_with_spo_scope` — mock `subprocess.run` to return fake JSON; assert `owa-piggy` invoked with `--audience spo --scope https://<host>/.default`.
- `test_setup_auth_missing_broker_raises_auth_error` — `shutil.which('owa-piggy') = None` → `AuthExpiredError`.
- `test_make_spo_refresh_lambda` — assert lambda calls `get_token` with correct args on invocation.

**`test_manifest.py`** (pure, no network):
- `test_parse_iso_duration_full_form` — `"PT1H2M3.5S"` → `3723.5`. Covers the `2cae29f` fix.
- `test_parse_iso_duration_seconds_only` — `"PT45S"` → `45.0`.
- `test_expand_timeline_normal` — `r=2` entry produces 3 start times.
- `test_expand_timeline_open_ended_r_minus_1` — `r="-1"` entry uses next `<S t=...>` as boundary. Covers the `2cae29f` fix.
- `test_expand_timeline_r_minus_1_uses_period_end` — `r="-1"` on the last segment uses `duration_s * timescale`.
- `test_parse_manifest_encrypted_raises_usage_error` — manifest with `ContentProtection` → `UsageError`.
- `test_parse_manifest_returns_track_dict` — synthetic DASH XML with video+audio tracks; assert track keys, `init`, `media_tmpl`, `times` list.

**`test_resolve.py`** (mocked network):
- `test_resolve_manifest_url_parses_docid_region_ctag` — call `resolve_manifest_url` with a synthetic URL; assert `Job` fields.
- `test_resolve_manifest_url_caches_region` — assert `config_mod.config_set` called with `region`.
- `test_resolve_embed_url_calls_spo_and_graph` — mock `Http.get` twice; assert `Job.drive_id`/`item_id`.
- `test_resolve_embed_url_missing_region_raises_usage_error`.

**`test_segments.py`** (mocked `Http`):
- `test_get_segment_success` — mock returns `(200, b'\x00' * 188)`; assert bytes returned.
- `test_get_segment_auth_retry_on_401` — first call returns `(401, b'')`, second returns `(200, data)`; assert `token_holder["refresh"]` called once and data returned. Covers `2cae29f` auth-retry fix.
- `test_get_segment_exhausted_retries_raises` — all 6 attempts return 401 with no refresh callable; assert `OwaError` raised.
- `test_download_track_resumes` — pre-create a valid `.m4s` in `workdir`; assert no fetch for that segment.
- `test_mux_calls_ffmpeg` — monkeypatch `subprocess.run`; assert called with `['-c', 'copy']`.

**`test_format.py`** (pure functions):
- `test_format_info_pretty_contains_title` — assert title/duration/resolution present in output string.
- `test_format_get_pretty_shows_path_and_size`.

**`test_config.py`** (uses `tmp_config` fixture):
- `test_load_config_returns_empty_on_missing_file`.
- `test_config_set_persists_region` — set `region`, reload, assert value.
- `test_config_set_rejects_unknown_key` — `config_set('bad_key', 'x')` → `UsageError`.
- `test_migrate_json_config_imports_old_keys` — write old-format `.json` file; call `load_config()`; assert region migrated and `.json` file deleted.

**`test_cli_commands.py`** (`_main()` dispatch, fully mocked):
- `test_main_schema_returns_tool_name`.
- `test_main_info_json_output` — mock `resolve_mod._resolve`, `manifest_mod._manifest`; assert stdout is valid JSON with `duration_s`.
- `test_main_info_pretty_output` — `--pretty` produces stdout text with title.
- `test_main_get_writes_file_and_outputs_json` — mock resolve + manifest + `download_track` + `mux`; assert `{"out": ..., "bytes": ..., "title": ...}` on stdout.
- `test_main_agent_mode_envelope` — `["--agent", "info", "--manifest-url", "..."]` → `_owa.tool == "owa-vids"`, `_owa.command == "info"`.
- `test_main_err_json_on_auth_failure` — broker absent → rc 11, stderr JSON with `error.code == "AUTH_EXPIRED"`.
- `test_main_config_verb_unauthenticated` — `cmd_config` runs without owa-piggy on PATH.
- `test_main_debug_flag_sets_config` — `--debug` propagates to config dict.

### Coverage gate

`owa_vids` is added to `[tool.coverage.run]source`. The per-tool `Http` class and segment loop have > 50% coverage via `test_segments.py` mocks. The `mux` function requires mocking `subprocess.run`. With the above test files, the overall coverage floor should be maintained; confirm with a dry-run before merging.

## Out of scope

- **`recap-dl.py` (AES-CBC decryption)**: dropped entirely. Not merged. If an encrypted manifest is encountered, `parse_manifest` raises `UsageError` with an informative message.
- **Live integration tests**: no test in this plan requires a real Microsoft 365 tenant. All tests mock at the `Http.get` or `subprocess.run` boundary.
- **`--out -` (pipe to stdout)**: binary-stdout mode for `get` is out of scope for v1.
- **Write operations** (upload, delete): `owa-vids` is a read-only consumer; no mutations, no `--confirm` machinery.
- **`owa-planner`/`owa-sites`/`owa-teams` staleness cleanup**: the plan fixes the stale entries in contract/architecture test lists while touching those files, but a full catch-up of those three tools' tests is not in scope here.

## Risks and open questions

1. **`owa_core.http` vs `owa_vids.http` boundary**: the keep-alive requirement is empirically derived from throttle behaviour on svc.ms. If `owa_core.http` gains a persistent-connection mode in a future refactor, `owa_vids/http.py` can be deleted. Until then, `Http` stays local and the architecture-contract test that enforces "all `urllib`/HTTP usage stays in `owa_core.http`" (`src/tests/test_architecture_contracts.py`) must exempt `owa_vids/http.py` explicitly — add it to that test's allowlist. **Confirm the exact test name and allowlist mechanism at edit time** (the survey inferred it; verify).

2. **`get_token` direct call inside `make_spo_refresh` lambda**: `_get_segment` calls `token_holder["refresh"]()` mid-download, which eventually calls `owa_core.auth.get_token(...)`. This is the only place in the suite that calls `get_token` directly (rather than `get_token_for_config`). The architecture contract that scans for raw `['owa-piggy', 'token'`/`['owa-piggy', 'profiles'` string literals must still pass — `owa_vids/auth.py` must not contain those literals; calls route through `owa_core.auth`. Verify the contract name/behaviour at edit time.

3. **Config format migration**: users of the standalone `owa-vids` script store config at `~/.config/owa-vids/config.json`. The monorepo version uses `~/.config/owa-vids/config` (no `.json`, `KEY="VALUE"` format). The `_migrate_json_config()` helper in `config.py` handles this transparently on first load, but if the migration is skipped (e.g. the file is read-only), `load_config()` silently returns defaults. Log a one-time warning to stderr via `_info()`.

4. **SPO host is not constant**: unlike every other owa-tools package, `owa-vids` has no single `API_BASE` constant. The SPO host (`spo_host`) is derived from the source URL at runtime. `auth.py` therefore cannot follow the standard `setup_auth(config, debug) -> (token, API_BASE)` two-tuple pattern exactly. The deviation is documented in Step 2 and Design Decision 4. If this creates friction with `run_with_output_modes` machinery, a sentinel `API_BASE = None` can be used and checked.

5. **Download-bypass disclosure**: `docs/vids.md` includes the single-sentence caveat per Design Decision 7. The caveat is present but not prominent (no warning box, no README headline). This is intentional and approved by the repo owner.

6. **ffmpeg runtime dependency**: ffmpeg is an external binary, not a Python package, so it does not violate the zero-third-party-PyPI-dep contract. However `owa-doctor`'s sibling probe and the Homebrew formula both need to know that ffmpeg is required. Add a `shutil.which('ffmpeg')` check inside `cmd_get` (not `cmd_info` or `cmd_check`) that raises a `UsageError` with a `remediation="Install ffmpeg: https://ffmpeg.org/download.html"` hint if absent.

7. **Pre-existing staleness in test lists**: `src/tests/test_architecture_contracts.py:RUNTIME_DIRS`, `src/tests/test_agents_index.py:RUNTIME_PACKAGES`, `src/scripts/check_stdlib_only.py:LOCAL_PACKAGES`, and `src/scripts/check_console_smoke.py:TOOLS` are all missing `owa_planner`, `owa_sites`, and/or `owa_teams` entries. These are fixed in Step 4/5 as a side-effect. Running the contract tests before this plan begins will show existing failures on those tools; they are not regressions introduced by this plan.
```
