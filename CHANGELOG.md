# Changelog

Suite changelog. `owa-tools` ships as one distribution, so all console
scripts share one version.

Format: append a `## vX.Y.Z` section when tagging a release, then use
per-tool subsections inside that release when useful.

## v0.2.0 (unreleased)

### owa-mail

- New: attachment support. `owa-mail attachments --id <id>` lists a
  message's attachments (name/type/size/kind, no base64 blob);
  `owa-mail attachment-get --id <id> --attachment <att-id>` downloads
  one file attachment to `--out <path>` or raw bytes on stdout.
- New: repeatable `--attach <file>` on `send`, `reply`, `reply-all`,
  and `forward`. Files 3 MB or smaller are sent inline; larger files
  transparently use a Microsoft Graph resumable upload session (create
  draft -> createUploadSession -> chunked PUT -> send), reusing the
  shared `owa_core.upload` driver. Small no-attachment sends keep the
  single-shot `sendMail` fast path.
- New: `owa-mail show --pretty` now renders HTML bodies as readable
  plain text instead of raw markup. A stdlib-only (`html.parser`)
  converter turns block elements into line breaks, bullets list items,
  drops `<script>`/`<style>`, unescapes entities, and collapses
  whitespace. JSON output is unchanged (raw `body` verbatim); text
  bodies pass through untouched.

### owa-drive

- New: `owa-drive put` now uploads files of any size. Payloads larger
  than 4 MB transparently use a Microsoft Graph resumable upload
  session (chunked PUTs to a pre-authorized URL); files at or under
  4 MB still take the single-PUT fast path. The previous hard cap and
  "not implemented" error are gone.

### owa_core

- New: `owa_core.upload.upload_session(upload_url, content, ...)`, a
  generic, stdlib-only, injectable driver for Graph upload sessions.
  It chunks bytes into 320 KiB-multiple PUTs against a pre-signed
  uploadUrl (no bearer token), retries transient 429/503 per chunk,
  and returns the final item JSON. Reused by owa-drive today and ready
  for mail attachments next.

## v0.1.3 - 2026-05-18

Improves the agent-facing CLI contract by adding per-subcommand help across the suite.

- New: every command in the per-tool schemas now supports `<tool> <command> --help` and `-h` without triggering auth, broker, or network setup.
- New: schema flags can describe values, required markers, and repeatability, so generated help explains the expected invocation shape.
- Tests: contract coverage now asserts every schema command renders subcommand help successfully.

## v0.1.2 - 2026-05-12

Adds the hugr CLI contract surface across the suite and fixes a batch of
contract-drift bugs caught by self-review. No breaking changes to the
0/2/10-20 exit-code taxonomy; the `--doctor` 0-5 taxonomy is a documented
carve-out.

- New: every `owa-*` binary now accepts a top-level `--doctor` flag that
  emits the shared hugr doctor payload (tool, suite version, findings).
  `owa doctor` still shells out to `owa-doctor` for back-compat.
- New: `owa_core.conventions` ports the hugr contract helpers
  (`action_envelope`, `data_error`, `DoctorPayload`, `DoctorFinding`,
  `EXIT_*` constants) and re-exports `owa_core.secrets.redact`.
- Fix: 43 sites across 12 `owa-graph` resource modules were emitting
  usage errors to stdout, corrupting JSON pipelines (`jq`, `--agent`
  mode, CI consumers). All now raise `UsageError`, hit stderr, and exit
  with code 2.
- Fix: webcal bearer-URL writes in `owa_cal/profiles.py` now use
  `mkstemp` + `fchmod(0o600)` + `fsync` + `os.replace`, closing a
  TOCTOU window where the secret was briefly world-readable.
- Fix: `owa-graph files search` now URL-encodes the OData term and
  escapes single quotes, so names like `O'Brien` no longer break the
  request.
- Fix: `owa_drive` `api_put_binary` raises `UsageError` on the 4MB
  guard, so callers exit 2 instead of 1.
- Contract: structured failure envelopes from `emit_data_error` now go
  to stdout (matching the hugr CONVENTIONS one-stream rule that
  `gh api`, `aws`, `kubectl -o json`, and `terraform output -json` also
  follow). Free-text errors, tracebacks, and progress still go to
  stderr.
- Tests: moved a hidden test file from `src/owa_core/tests/` into
  `src/tests/core/` so pytest's `testpaths` discovers it. Coverage
  jumped from 84% to 97% on `owa_core`.
- Docs: README points at the hugr suite. `AGENTS.md` documents the
  `--doctor` 0-5 carve-out alongside the main exit-code taxonomy.

## v0.1.1 - 2026-05-11

Internal repo restructure. No user-visible behavior change: the wheel,
console scripts, import paths, and distribution metadata are identical
to v0.1.0.

- Collapse top-level layout under `src/`. All runtime packages
  (`owa`, `owa_cal`, `owa_core`, `owa_doctor`, `owa_drive`, `owa_graph`,
  `owa_mail`, `owa_people`, `owa_sched`) plus `tests/`, `completions/`,
  `packaging/`, and the former `tools/` (renamed to `scripts/`) now live
  under `src/`. The repo root keeps only `docs/`, `src/`, dotfolders,
  and top-level markdown so the README sits higher on GitHub.
- `pyproject.toml` switches to src-layout via `package-dir`. CI
  workflows, helper scripts, AGENTS.md mesh, and contributor docs
  retargeted accordingly.

## v0.1.0 - 2026-05-10

First public suite release. `owa-tools` consolidates the seven legacy per-tool
installs (`owa-cal`, `owa-mail`, `owa-graph`, `owa-doctor`, `owa-people`,
`owa-sched`, `owa-drive`) plus the new umbrella `owa` discovery binary into
one distribution. Auth still goes through `owa-piggy` as a separate package
via its subprocess JSON contract.

Suite-wide:

- Stdlib-only at runtime. No third-party deps.
- One suite version across all eight binaries.
- `owa list`, `owa schema`, `owa doctor`, `owa version` umbrella commands.
- Verified compatible with `owa-piggy` 0.8.0 (minimum supported 0.7.1).
- Release flow: PyPI via local `uv publish` (UV_PUBLISH_TOKEN from `.env`);
  GitHub Actions builds artifacts and creates the GitHub Release.
- Draft Homebrew formula at `packaging/homebrew/owa-tools.rb`.


### owa-cal

### owa-mail

### owa-graph

### owa-doctor

### owa-people

### owa-sched

### owa-drive

### owa (umbrella)

Thin discovery binary. Subcommands:

- `owa list` - JSON list of installed consumers and their versions.
- `owa schema [--tool <name>]` - aggregate `<tool> schema` output.
- `owa doctor [...]` - forwards to `owa-doctor probe`.
- `owa version` - umbrella version.

Real work lives in the per-tool binaries.
