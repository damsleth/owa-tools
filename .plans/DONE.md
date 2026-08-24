# Done

Completed plans, newest first. The detailed plan files move to
[`.plans/done/`](done/) as historical record, each with a status banner
pointing back here.

- **swodp-cli** — new `owa-swodp` sibling implemented: prod/UAT-isolated Edge
  sidecars, silent CDP cookie + `g_ck` capture, Table API status/read commands,
  optional per-table 403 degradation, exact write-row validation, and
  Pending-only write plans with POST → PATCH → GET description verification.
  Live prod status/full-sync reads passed; remote mutation remains UAT-first
  and was not attempted because no UAT sidecar exists yet. (2026-08-21)
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
