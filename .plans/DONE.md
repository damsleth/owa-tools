# Done

Completed plans, newest first. The detailed plan files move to
[`.plans/done/`](done/) as historical record, each with a status banner
pointing back here.

- **swodp-cli** — new `owa-swodp` sibling implemented: prod/UAT-isolated Edge
  sidecars, silent CDP cookie + `g_ck` capture, Table API status/read commands,
  optional per-table 403 degradation, exact write-row validation, and
  Pending-only write plans with POST → PATCH → GET description verification.
  Live production verification passed on 2026-08-24: create, Pending-only
  update, delete, description persistence, and locked-card refusal (exit 15)
  all confirmed against the real instance, with the baseline restored. Two
  findings: `task <unknown>` exited 0 with `null` (fixed to exit 13), and
  `rtk proxy` corrupts JSON reads badly enough to invalidate a pre-write
  snapshot — verification reads must use the bare binary. Session-expiry
  behavior is an accepted documented residual risk.
  Also added `submit` (Service Portal `timecardprocessor.do` processor, not the
  Table API) and `delete` for a single card by `sys_id`, both Pending-only with
  the guard verified live. Released as v1.5.0 on 2026-08-24: PyPI, CI-built
  GitHub Release, Homebrew tap, clean-install verified.
  (2026-08-21, verified and released 2026-08-24)
  Plan: [done/swodp-cli.md](done/swodp-cli.md).

- **owa-planner-write-support** — mutating half of owa-planner shipped:
  `@odata.etag` preserved through `normalize_*`, `api_post/patch/delete` with
  `If-Match`, `create/update/delete-task` + `update-task-details` +
  `update-plan-details` commands with a `_require_etag` guard, stale-etag 412 →
  exit 15. Found already-implemented when revisited; closed the one gap (a
  stale-etag conflict test). (2026-06-29)
  Plan: [done/owa-planner-write-support.md](done/owa-planner-write-support.md).

- **exit-code-taxonomy-fix** (P0) — the documented exit-code taxonomy (10
  network / 13 not-found / 14 rate-limited / 15 conflict / 20 internal) now
  actually reaches the shell instead of collapsing to 1. Every networked
  `api.py` raises its recoverable `OwaError` (was `emit_error` + `return None`);
  the central `run_with_output_modes` → `emit_error` returns the right code.
  Cleaned up the last 4 swallow spots (upload-session paths in owa-mail/-drive)
  and added an end-to-end contract test on owa-cal. (2026-06-29)
  Plan: [done/exit-code-taxonomy-fix.md](done/exit-code-taxonomy-fix.md).

- **owa-vids merge** — standalone `owa-vids` script merged into the monorepo
  as the thirteenth binary: token-only Teams/OneDrive meeting-recap DASH
  downloader (`info`/`get`/`check`/`config`), refactored onto `owa_core`
  primitives with one sanctioned exception (`owa_vids.http.Http` keep-alive
  for svc.ms). Shipped in **v0.8.0** (`d2f5502`, 2026-06-03,
  `feat(owa-vids): add meeting-recap video downloader as 13th binary`),
  released 2026-06-05 with a Homebrew tap bump.
  Plan: [done/merge-owa-vids.md](done/merge-owa-vids.md).

- **owa-teams** — read-only Microsoft Teams consumer CLI (`teams`, `channels`,
  `chats`, `messages`, `meetings`) over Graph + the chatsvc `teams` audience.
  Phase 1 shipped in **v0.7.0** (`eadbfb8`, 2026-06-02,
  `feat(owa-teams): add Microsoft Teams consumer CLI (read-only)`); 429
  Retry-After ride-through followed in `7d076fe` (2026-06-03). Open follow-ups
  (`messages --since`, `messages --region`) tracked in [TODO.md](TODO.md).
  Plan: [done/owa-teams.md](done/owa-teams.md).

- **owa-shifts** — CLOSED, NOT BUILT: blocked by client preauth
  (`AADSTS65002` — the StaffHub resource `aa580612` does not preauthorize
  owa-piggy's One Outlook Web client, and it isn't FOCI), and the Graph
  `/teams/{id}/schedule` door has no data. Probed 2026-06-01; archived
  without building. Plan: [done/owa-shifts.md](done/owa-shifts.md).

- **owa-mail TUI overhaul** — full-width layout, reading pane, search-400 fix,
  esc overlay menu + persisted settings. Shipped `23b5f21` (2026-06-01),
  `feat(mail): full-width tui with reading pane, esc menu, and settings`.
  Plan: [done/owa-mail-tui-esc-menu-and-settings.md](done/owa-mail-tui-esc-menu-and-settings.md).

- **owa-doctor siblings cross-check** — `owa-doctor --json` `siblings[]` entries
  are now asserted schema-compatible with each binary's own `<binary> --doctor
  --json` payload. Shipped `b290aa1` (2026-05-29),
  `test(doctor): cross-check siblings[] against per-binary --doctor schema`.
  Plan: [done/owa-doctor-siblings-crosscheck.md](done/owa-doctor-siblings-crosscheck.md).

- **multi-profile fan-out** — repeated `--profile` fans out across profiles via
  the shared `owa_core.modes.run_with_output_modes` entry point (every CLI
  gained it with zero per-tool code; `owa-doctor` opts out). Foundation shipped
  in v0.6.1 (`10cdaff`, 2026-06-02); the post-release follow-up (per-command
  `--help` block, prose docs across `profile-model.md`/README/AGENTS/skill, and
  per-tool end-to-end tests) shipped in **v0.6.2** (`c81f27e`, 2026-06-02) —
  commits `9316e7f` (docs), `22097d3` (tests), `ad684fe` (plans housekeeping).
  Plan Status: COMPLETE —
  [done/multi-profile-simultaneous-calls.md](done/multi-profile-simultaneous-calls.md).

  **Released v0.6.2 (2026-06-02), all channels:** tag `v0.6.2` + GitHub Release
  (CI workflow green, wheel + sdist attached); PyPI
  [`owa-tools 0.6.2`](https://pypi.org/project/owa-tools/0.6.2/) (wheel + sdist);
  Homebrew tap `damsleth/homebrew-tap` bumped 0.5.0 → 0.6.2
  (`Formula/owa-tools.rb`, GitHub source archive). cj-owa-tools skill updated in
  `skills-private`. (Patch bump: docs + tests over already-shipped behaviour.)
- [x] owa --pretty: render shallow/simple objects (e.g. owa-graph get /me) as a table instead of JSON; make --pretty do more than just pretty-print JSON (2026-06-15)
- [x] owa-teams `messages --region <emea|amer|…>` — per-call region override so multi-region profiles don't depend on single-valued config (2026-06-16)
- [x] owa-teams `messages --since <iso>` — stop following `backwardLink` past the cutoff (closes yaams' cold-start history gap) (2026-06-16)
- [x] add owa-mail functionality for resetting settings to default (2026-06-16)
- [x] add owa-mail "all inboxes" view across multiple/all stored profiles (2026-06-16)
- [x] P2 suite-wide: OData passthrough (--select/--filter/--orderby/--expand) where missing (graph/mail/people/todo/planner/sites); config --unset/clear (planner/sites/ado) (2026-06-30)
- [x] P2 owa-doctor: broker-reachability + audience-mismatch warning, multi-audience/scope-coverage check, --timeout, repeatable --profile/subset (2026-06-30)
- [x] P2 owa-ado: --all on prs/runs, wi comment + relation/link mgmt + wi-delete, --api-version escape hatch (2026-06-30)
- [x] P2 owa-teams: paging on chats/channels (--top/--all), message send/reply, members command, structured mentions/attachments arrays, --html raw body option (2026-06-30)
- [x] P2 owa-sites: --all/paging on items (silent 50-page cap), $filter/$orderby/$expand, by-id/by-URL addressing, item/file detail by id (2026-06-30)
- [x] P2 owa-todo: --reminder, --recurrence, --category on write, undone/uncomplete command, lists create/rename/delete, server-side $filter/$orderby (2026-06-30)
- [x] P2 owa-people: manager/direct-reports/org-chart, contact CRUD, photo, presence (verify scope), group membership, --top alias, --select/--filter passthrough (2026-06-30)
- [x] P2 owa-graph: --max-pages safety valve on --all, reconcile --raw/--curl/--az with --agent (binary_stdout_commands), force graph audience for batch (2026-06-30)
- [x] P2 owa-mail: attachment-get fallback for item/reference attachments (no $value), move-by-display-name + copy command, --orderby/--skip, categories set/filter, --has-attachments/--importance filters, thread/conversation command (2026-06-30)
- [x] P2 owa-cal: add attendees on create/update, --reminder, repeatable --category, recurrence; send Prefer outlook.timezone on calendarView window (off-by-one near midnight) (2026-06-30)

## Reconciled 2026-09-08

Moved these 12 already-completed historical entries out of TODO. Original completion dates and wording are preserved. The old Drive overwrite closure is superseded by current review finding R1; it is not evidence that the current guard is safe. The cleanup entry also overstates removal of dead wrappers, which remain in several adapters.

- [x] **exit-code taxonomy collapses to 1** — DONE 2026-06-29: every `api.py` now `raise`s the recoverable OwaError (cal/mail/graph/drive/people/sched/todo/planner/sites/teams already converted; ado raises by design); the central `run_with_output_modes` → `emit_error` returns `int(error.exit_code)`. Fixed the last 4 swallow-and-return-None spots (upload-session paths in owa-mail/owa-drive). Added end-to-end contract test (`test_recoverable_errors_propagate_documented_exit_code`, owa-cal) asserting 10/13/14/15/20 reach the shell. Plan archived to done/. See [done/exit-code-taxonomy-fix.md](done/exit-code-taxonomy-fix.md).
- [x] P0 owa-drive: put --force silently overwrites files >4MiB — RESOLVED earlier: the `_remote_exists` + `--force` preflight (exit 15) gates both the small PUT and the large upload-session path, so no silent overwrite. Per-file fail/replace/rename granularity remains a P2 nice-to-have, not data-loss.
- [x] P0 owa-drive: get --out clobbers existing local file silently — FIXED: refuses with exit 15 unless --force
- [x] P0 owa-ado: PR --repo interpolated unencoded into request path — FIXED: quote(repo, safe='') + build_url keeps '%' safe
- [x] P1 suite-wide cleanup (post exit-code refactor): DONE — deleted the dead `try/except OwaError: raise` wrappers + `_handle_owa_error` (owa-ado/owa-drive), removed unreachable `if x is None: return 1` guards, fixed stale docstrings; hoisted `build_query` into owa_core/query.py (6 importers) and `_require_value` into owa_core.errors (all tools).
- [x] P1 owa-graph: drop stale --app-client-id from config help text — DONE
- [x] P1 owa-sites: positional --site — NO-OP: cmd_site already accepts the bare positional via pop_positional_id (line 139) and the help/schema already say "flag or positional"; regression tests test_site_positional + test_main_routes_site exist. Stale finding.
- [x] P1 owa-people: dead show comment describes email-vs-id branching — DONE: comment corrected (Graph /users accepts both UPN and id at one endpoint, no branching needed)
- [x] P1 owa-cal: wire dead-but-tested normalize_event_detail into a show --id command — DONE (`owa-cal show --id <id>`)
- [x] P1 owa-ado: wire --iteration to build_wiql(iteration=); validate --status — DONE
- [x] P1 owa-teams: rename messages --all → --system-events; add truncation signal at page cap — DONE
- [x] P1 owa umbrella: route meta-commands (list/schema/version) through run_with_output_modes — DONE (meta-commands now honor --agent/--err-json); schema built in-process via importlib import of each tool's COMMAND_SCHEMA, no more 13 subprocesses.

- **Legacy TUI backlog retired from this repository**, not completed: built-in TUIs were removed in `bbfc1c0`; CLI-only cleanup followed in `c73ce32`. Original fragments and completed calendar TUI note are preserved in [done/legacy-todo-2026-09-08.md](done/legacy-todo-2026-09-08.md). No sibling repository was modified.
- [x] P1 R1: make Drive no-force uploads fail closed and enforce server-side no-overwrite (2026-09-09)
- [x] P1 R11: validate SWODP split replacements before deleting existing Pending cards; retain partial-progress evidence (2026-09-09)
- [x] P1 R4/R5/R9: close escaped-body, fan-out error, and signed-URL logging leaks (2026-09-09)
- [x] P1 R2/R3: make scheduling output JSON-safe and refuse free-time claims for failed attendees (2026-09-09)
- [x] P2 R6/R7: fix fan-out exit-status consistency and canonical binary-command guards (2026-09-09)
- [x] P2 R8: map transport timeouts and interrupted reads to typed network errors (2026-09-09)
- [x] P2 R10: propagate Teams page-cap truncation to CLI results (2026-09-09)
- [x] P2 R12: stop org-chart manager traversal cleanly on top-of-chain 404 (2026-09-09)
- [x] P2 review follow-ups: verify scheduling timezones and frozen Graph data assets; reconcile semantic docs drift (see ../.tmp/reviews/2026-09-08/REVIEW.md) (2026-09-09)
- [x] owa-ado: add `pr-create`. Opening a PR is the one release step the CLI cannot do, so it falls back to the portal or to raw REST. Hit on 2026-09-14 opening NOCOS-Main `test` -> `main` (PR 3869), which had to go through `POST _apis/git/repositories/{repo}/pullrequests` with an owa-piggy `devops` token; `az devops` is no help, it wants its own `az devops login` even with `az account` signed in. Mirror `wi-create`: `--source`/`--target` refs, `--title`, `--description` (accept `-` for stdin, descriptions are long), `--repo`, `--draft`, `--confirm`. Read back `mergeStatus` and `hasConflicts` after create, the way the swodp commands verify their own writes. (2026-09-21)
