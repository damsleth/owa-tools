# Changelog

Suite changelog. `owa-tools` ships as one distribution, so all console
scripts share one version.

Format: append a `## vX.Y.Z` section when tagging a release, then use
per-tool subsections inside that release when useful.

## Unreleased

### owa-sites

- New tool: a read-only SharePoint CLI that talks to the **SharePoint REST API**
  on the per-tenant `*.sharepoint.com` host. `site` shows a site web, `lists`
  lists its lists/libraries, `items --list <title>` reads list items, `files
  --path <server-relative>` lists a folder's files, and `search --q <text>` runs
  a tenant search for sites and content. JSON on stdout, `--pretty` for humans.
  Auth mints a SharePoint-resource token via owa-piggy's `--scope` override
  (`https://<tenant>.sharepoint.com/.default`, carrying `Sites.FullControl.All`);
  the tenant host is auto-discovered from `/organization` verifiedDomains (or
  pinned with `config --host`). This is distinct from `owa-graph sites`, which
  rides the Graph `/sites` API and 403s without `Sites.Read.All`. File download
  and upload are deferred.

### owa-planner

- New tool: a read-only Microsoft Planner CLI. `plans` lists my plans (or a
  group's with `--group`), `buckets --plan <id>` lists a plan's buckets,
  `tasks` lists my assigned tasks (or a plan's with `--plan`, filtered by
  `--bucket` / `--status`), and `task <id>` shows one task merged with its
  checklist and description. Reads the Microsoft Graph `/planner` surface on the
  `graph` audience — authorized by `Group.ReadWrite.All`, so no `Tasks.*` scope
  is required. JSON on stdout, `--pretty` for humans. Writes are deferred
  (Planner PATCH needs the exact `@odata.etag` in `If-Match`).

## v0.6.0 - 2026-06-01

Headline: the `owa-mail tui` gets a real reading experience. The list now
fills the full terminal width, a reading pane (default on the right) previews
the selected message's body — lazily fetched and cached — and an `Esc` overlay
menu exposes persisted settings. Vim-style focus navigation moves between the
list and the pane.

### owa-mail

- New: reading pane in the TUI showing the selected message body, with
  placement `off` / `right` / `bottom` and a configurable list/pane split
  ratio. The body is fetched on demand and cached per message.
- New: full-width list layout — columns flex to fill the terminal instead of
  topping out at a fixed width.
- New: `Esc` overlay menu (Resume / Settings / Help / Quit). The Settings
  screen persists to `~/.config/owa-mail/config` and configures the reading
  pane placement, split ratio, sort order (date newest/oldest, sender,
  subject, unread-first) and date format (ISO 8601, `DD.MM`, `DD.MM HH:MM`, or
  a custom strftime string).
- New: focus navigation — `l`/`→` enters the reading pane (`j`/`k` then scroll
  the body, `h`/`←` returns to the list); `u`/`d` half-page up/down in the
  focused region; `Enter` still opens the full-screen reader; `q` quits.
- Fixed: TUI search no longer returns HTTP 400. `$search` and `$orderby` are
  mutually exclusive in Outlook/Graph, so `build_list_query` now drops
  `$orderby` when a search is present.
- Fixed: `messages --search` JSON output is sorted newest-first client-side
  again (the API returns relevance order once `$orderby` is dropped); `--pretty`
  already sorted on its own.

## v0.5.0 - 2026-05-29

Headline: `owa-graph --curl` / `--az` no longer leak a live bearer token.
By default the rendered command carries a `$OWA_TOKEN` placeholder, so
`owa-graph GET /me --curl | pbcopy` is safe to copy into the clipboard,
chat, or shell history. `owa-mail messages` gains `--with-body`, and the
maintainer reference docs (architecture, testing, onboarding) now ship
in `docs/`.

Behavior change: anyone parsing the live access token out of
`owa-graph ... --curl`/`--az` output must now pass `--include-token` to
inline the real bearer. The placeholder is the new default.

### owa-graph

- Fixed: `--curl` and `--az` render `Authorization: Bearer $OWA_TOKEN`
  (double-quoted so the shell expands it at run time) instead of inlining
  the real access token. A stderr note points at
  `export OWA_TOKEN=$(owa-piggy token --audience <aud>)`.
- New: `--include-token` opts back into inlining the real bearer for
  `--curl`/`--az` when you explicitly want a self-contained command.

### owa-mail

- New: `--with-body` on `messages` fetches message bodies inline,
  skipping the per-message `show` roundtrip.

### Docs

- New maintainer reference docs baked into `docs/`: `architecture.md`
  (low-entropy architecture and the shared `owa_core` contract layer),
  `testing.md` (test layers, fixtures, coverage gates), and
  `new-tool-onboarding.md` (the process for adding a console script).
  `security.md` gains a threat-model section. The root and package
  `AGENTS.md` files now point agents at these as read-first reference.

## v0.4.0 - 2026-05-28

Headline: `owa-drive put` learns batch mode and refuses to overwrite by
default (use `--force`). Pre-auth argument validation across the suite
so usage errors fail fast with exit `2` instead of exit `11` ("owa-piggy
not found") on machines without the broker. Coverage in CI is now
line+branch.

Breaking: scripts that relied on `owa-drive put <local> <remote>`
silently overwriting an existing remote item must now pass `--force`.
The default behavior is to refuse with exit `15` (CONFLICT). OneDrive
versioning preserves the previous content, so this is a bandwidth
guard rather than a data-loss guard.

Resolves four findings from the 2026-05-27 review
(`.plans/done/2026-05-27-review.md`).

### CLI contract

- Fixed: missing required flags now exit `2` (UsageError) on every
  authed command (mail/cal/drive/sched/people/todo/graph) instead of
  exit `11` ("owa-piggy not found") on machines without the broker. A
  new `owa_core.schema.precheck_required_args()` is wired into each
  dispatcher and runs *before* `setup_auth()`, so invalid invocations
  fail fast and don't make a broker round-trip. Remaining
  `_error(...); return 1` patterns across the suite were converted to
  `raise UsageError(...)` so usage exit codes are uniform.
- Fixed: unknown commands (`owa-cal frobnicate`) and missing
  flag-values (`--profile` with no argument) now exit `2` instead of
  `1`, matching the shared error taxonomy.

### owa-drive

- New: `--force` flag on `put`. By default, `owa-drive put` refuses to
  overwrite an existing remote item and exits `15` (`ConflictError`).
  OneDrive enables file-version history on every drive, so the refusal
  is a bandwidth optimization (skip the upload bytes when the remote
  already has the file) rather than a data-loss guard.
- New: batch upload. `owa-drive put <local1> <local2> ... <remote-dir>`
  uploads many local files to one remote directory, mapping each to
  `<remote-dir>/<basename>`. Existing files are **skipped, not
  refused** so the rest of the batch keeps going; per-file failures
  are recorded in the JSON summary's `failed` list but never abort the
  run. Exit `0` when `failed` is empty (skips count as success), `1`
  otherwise. `--force` overwrites and skips the existence preflight.
- Reading `-` (stdin) is rejected in batch mode (no basename to map).

### Packaging

- Fixed: Homebrew formula (`src/packaging/homebrew/owa-tools.rb`) no
  longer asserts `owa doctor --no-tokens` exits `0`. `owa-doctor`
  deliberately exits `2` when `owa-piggy` is not installed (the broker
  is required for any real check), and `brew test` runs without
  `owa-piggy` on PATH. The formula now uses `shell_output(..., 2)` and
  asserts on the `"installed": false` JSON payload. Also adds
  `owa-todo` to the formula's binary list (was missing).

### Tooling

- New: `check_no_stale_per_tool_installs` in
  `src/scripts/check_docs_sync.py` flags any
  `brew/pipx/pip install <owa-cal|owa-mail|owa-graph|owa-doctor|
  owa-people|owa-sched|owa-drive|owa-todo>` snippet that slips back
  into `docs/` or `README.md`. The suite ships as one distribution
  (`owa-tools`); per-tool packages no longer exist.

### CI / coverage gates

- Changed: coverage now runs with `branch = true`, so the gates
  measure every dispatch path rather than just statement reach.
  `owa_core` stays on a 95% line+branch gate (currently 96%); the
  runtime tree gate is now 89% line+branch (currently 89.39%). The
  per-tool line-only number was 91.38% before branch was enabled - the
  gate dropped 1 point because branch coverage is stricter, not
  because tests regressed. The 89% floor is the honest combined number
  we will ratchet upward as `owa_todo` / `owa_people` / `owa_sched`
  coverage closes the remaining gap.
- Changed: `ci.yml` and `release.yml` updated to invoke the new gates.
- Fixed: `src/scripts/check_console_smoke.py` was missing `owa-todo`
  from its `TOOLS` tuple, so the fresh-venv smoke step in CI silently
  skipped the ninth binary. All nine consumer CLIs are now exercised
  on every push.

## v0.3.1 - 2026-05-27

The 0.3 feature set ships as v0.3.1. The v0.3.0 tag was pushed but never
published: 0.3.0 declared a hard runtime dependency on `hugr-conventions`,
which is not on PyPI, so the wheel was uninstallable
(`No matching distribution found for hugr-conventions>=0.1`) and its
release CI failed at the install step before producing any artifact (no
GitHub Release, nothing on PyPI). Per "fix forward, don't force-push
tags," the dead tag is left in place and the features land here.

### Packaging

- Fixed: `owa-tools` is stdlib-only again with **no third-party runtime
  dependency**. The shared `hugr-conventions` package introduced in the
  0.3 line is dropped; the CLI-contract surface (action/error envelopes,
  NDJSON helpers, the doctor payload, and the 0-5 `--doctor` exit-code
  taxonomy) is vendored back into `owa_core.conventions` as a
  self-contained hand-copy. Public surface and behavior are unchanged.

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

### suite-wide (CLI uniformity)

- New: `owa-drive` accepts suite-canonical aliases for its unix verbs -
  `list` (=`ls`), `download` (=`get`), `upload` (=`put`), `delete`
  (=`rm`). The unix names remain the primary form; both work.
- New: every opaque-id command on `owa-cal`, `owa-mail`, and `owa-todo`
  now accepts the id either via `--id` or as a bare positional argument
  (`owa-mail show <id>` == `owa-mail show --id <id>`), matching the
  positional style of `owa-people`/`owa-drive`.
- New: every binary's `--help` now ends with a uniform "Machine surface"
  block documenting `schema`, `--help --json`, `--agent`, `--err-json`,
  and `--doctor`. The contracts already existed; they were previously
  undocumented in per-tool help.
- Fixed: `owa-doctor` now probes `owa-todo` (the sibling list had drifted
  and omitted the newest tool); the umbrella and doctor tool lists now
  derive from one registry (`owa_core.registry`) so they can't diverge.
- Fixed: `owa-sched availability` now honours the configured work-day
  window (`default_work_start`/`default_work_end`); it previously
  hard-coded 08:00-17:00 while `find-time` respected config.
- Changed: `owa-cal` and `owa-todo` now clamp `--limit` to `[1, 200]`
  (matching `owa-mail`'s cap); schema flag summaries, `idempotent`
  metadata on mutating commands, and the `--limit`/`--pretty`/`--profile`
  wording are now consistent across all tools.
- Docs: per-tool docs normalized, install instructions corrected to the
  one-distribution model, and `docs/profile-model.md` rewritten to match
  the real `owa-piggy` surface (`OWA_PROFILE`, plaintext-0600 profile
  store, `owa-piggy status`).

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
