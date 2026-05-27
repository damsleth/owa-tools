# Changelog

Suite changelog. `owa-tools` ships as one distribution, so all console
scripts share one version.

Format: append a `## vX.Y.Z` section when tagging a release, then use
per-tool subsections inside that release when useful.

## Unreleased

### owa-todo (new tool)

- New: `owa-todo`, a Microsoft To Do task CLI, joins the suite as the
  ninth console script. Commands: `lists` (task folders), `tasks`
  (list/filter by folder/status/subject), `create`, `update`, `done`
  (mark completed), `delete` (confirmation-gated), plus `config` and
  `refresh`. Reachable directly or via the umbrella (`owa todo tasks`).
- It targets the Outlook REST v2.0 Tasks API
  (`https://outlook.office.com/api/v2.0/me/taskfolders` and `.../me/tasks`)
  on the existing `outlook` audience — the same token owa-cal/owa-mail
  use, which already carries `Tasks.ReadWrite` on a To Do-capable
  profile. No owa-piggy change required. Tenants with strict Conditional
  Access that withhold the Tasks scope get a clean exit 12; switch
  profiles with `--profile`.
- `--all` pagination, `--pretty` output, and the shared exit-code /
  `--agent` / `--err-json` contracts work as on every other tool.

### owa (umbrella)

- New: `owa <tool> [args...]` now dispatches to any consumer CLI, so
  `owa cal events --week 16` is equivalent to `owa-cal events --week 16`.
  Everything after the tool name passes straight through; the tool's own
  `--help`/`--version`/`schema` and the `--agent`/`--err-json`/`--doctor`
  modes apply unchanged. Dispatch is in-process (all tools ship in one
  distribution, so the package is always importable - no subprocess) and
  propagates the tool's exit code. Both short (`cal`) and binary
  (`owa-cal`) forms resolve. Meta commands (`list`, `schema`, `version`,
  `--doctor`) keep precedence and are unchanged. `owa doctor` now routes
  through generic dispatch to `owa-doctor` (which defaults to `probe`),
  instead of shelling out with an inserted `probe` subcommand - behavior
  is equivalent.
- Internal: every tool's `main()` now accepts an optional `argv`
  (defaulting to `sys.argv[1:]`), which the umbrella passes when
  dispatching.

### owa-cal

- New: `owa-cal respond --id <id> --action accept|decline|tentative`
  sends a meeting reply to an invite via the Outlook REST
  accept/decline/tentativelyAccept actions. `--comment "<text>"`
  attaches a note for the organizer; the organizer is notified by
  default, and `--no-notify` records the response without sending a
  reply. On success it emits a confirmation envelope
  (`{"id", "action", "notified"}`) rather than an event, since Outlook
  returns no body for these actions. Rejected against webcal/iCal
  profiles (read-only feeds), like the other write commands.

## v0.2.1 - 2026-05-27

The 0.2 feature set ships as v0.2.1. The v0.2.0 tag was pushed but never
published: its release CI failed on a lint gate before producing any
artifact (no GitHub Release, nothing on PyPI). Per "fix forward, don't
force-push tags," the dead tag is left in place and the features land
here unchanged.

### Suite-wide

- New: `--all` pagination parity. Every list-producing command that
  returns a Graph-style `value` collection now accepts `--all` to follow
  `@odata.nextLink` until the collection is exhausted, matching
  `owa-graph`. Affected commands: `owa-mail messages`, `owa-mail
  folders`, `owa-people directory`, `owa-people contacts`, `owa-drive
  ls`, and `owa-cal events`. (`owa-people find` is excluded: `/me/people`
  is relevance-ranked and returns no `@odata.nextLink`.) Without `--all`
  behavior is unchanged (single page); with `--all`, `--limit`/`--top`
  still controls the page size requested per round-trip. All tools share
  the `owa_core.http.paginate` generator via a per-tool `paginate_all`
  helper that preserves the single-page error contract. (`owa-sched`
  uses a single POST `getSchedule` call with no `@odata.nextLink`, so it
  is unaffected; `owa-cal events` over a webcal/iCal profile treats
  `--all` as a no-op since the feed is always fetched in full.)

### owa-mail

- New: `--all` on `messages` and `folders` (see Suite-wide).
- New: attachment support. `owa-mail attachments --id <id>` lists a
  message's attachments (name/type/size/kind, no base64 blob);
  `owa-mail attachment-get --id <id> --attachment <att-id>` downloads
  one file attachment to `--out <path>` or raw bytes on stdout.
- New: repeatable `--attach <file>` on `send`, `reply`, `reply-all`,
  and `forward`. Each attachment's MIME type is detected from its
  filename. Files 3 MB or smaller are sent inline; larger files
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

### owa-people

- New: `--all` on `directory` and `contacts` (see Suite-wide).

### owa-cal

- New: `--all` on `events` (see Suite-wide).

### owa-drive

- New: `--all` on `ls` (see Suite-wide).
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
