# TODO

> **Priority legend** (suite-wide review, 2026-06-23 — see findings section below)
> - **P0** — correctness / data-loss / contract violations. Do first.
>   The systemic exit-code bug is plan-sized: [exit-code-taxonomy-fix.md](exit-code-taxonomy-fix.md).
> - **P1** — cheap, agent-facing drift / dead code / misleading help. High value/effort ratio.
> - **P2** — feature gaps (missing params, switches, commands). Schedule per roadmap.
>
> Two findings are large enough to be standalone plans:
> [owa-planner-write-support.md](owa-planner-write-support.md),
> [owa-sched-findmeetingtimes.md](owa-sched-findmeetingtimes.md).

- [ ] optional --pretty renderer for action commands (low priority; only if a human renderer is wanted)

## Suite review findings (2026-06-23)

### P0 — correctness / contract
- [ ] **exit-code taxonomy collapses to 1** across all 11 networked tools — see [exit-code-taxonomy-fix.md](exit-code-taxonomy-fix.md) (plan)
- [x] P0 owa-drive: put --force silently overwrites files >4MiB — RESOLVED earlier: the `_remote_exists` + `--force` preflight (exit 15) gates both the small PUT and the large upload-session path, so no silent overwrite. Per-file fail/replace/rename granularity remains a P2 nice-to-have, not data-loss.
- [x] P0 owa-drive: get --out clobbers existing local file silently — FIXED: refuses with exit 15 unless --force
- [x] P0 owa-ado: PR --repo interpolated unencoded into request path — FIXED: quote(repo, safe='') + build_url keeps '%' safe

### P1 — cheap, agent-facing
- [ ] P1 suite-wide cleanup (post exit-code refactor): the per-tool api.py `try/except OwaError: raise` blocks are now no-ops — owa_core.http already raises the typed errors (the new owa_places/api.py shows the correct bare shape). Delete the dead wrappers + `_handle_owa_error` (owa-ado/owa-drive), the leftover `if x is None: return 1` guards, and the stale module docstrings still describing the abandoned "returns None on 404/429" contract. Also hoist the verbatim-duplicated `build_query` (6x) and `_require_value` (3x) into owa_core. Found during the 2026-06-23 code review.
- [ ] P1 owa-graph: drop stale --app-client-id from config help text (cmd_config does not accept it)
- [ ] P1 owa-sites: schema/help claim positional --site but cmd_site only parses the flag — reconcile one or the other
- [ ] P1 owa-people: dead show comment describes email-vs-id branching that was never written — fix comment or implement
- [ ] P1 owa-cal: wire dead-but-tested normalize_event_detail into a show --id command (attendees/organizer/body)
- [ ] P1 owa-ado: wire --iteration flag to existing build_wiql(iteration=) dead param; validate --status (ADO has no all status)
- [ ] P1 owa-teams: rename messages --all (include system events) — collides with suite-wide --all=exhaust-pages; add truncation signal at page cap
- [ ] P1 owa umbrella: route meta-commands (list/schema/version) through run_with_output_modes for --agent/--err-json/--pretty; build schema in-process not via 13 subprocesses

### P2 — feature gaps
- [ ] P2 owa-cal: add attendees on create/update, --reminder, repeatable --category, recurrence; send Prefer outlook.timezone on calendarView window (off-by-one near midnight)
- [ ] P2 owa-mail: attachment-get fallback for item/reference attachments (no $value), move-by-display-name + copy command, --orderby/--skip, categories set/filter, --has-attachments/--importance filters, thread/conversation command
- [ ] P2 owa-graph: --max-pages safety valve on --all, reconcile --raw/--curl/--az with --agent (binary_stdout_commands), force graph audience for batch
- [ ] P2 owa-people: manager/direct-reports/org-chart, contact CRUD, photo, presence (verify scope), group membership, --top alias, --select/--filter passthrough
- [ ] P2 owa-todo: --reminder, --recurrence, --category on write, undone/uncomplete command, lists create/rename/delete, server-side $filter/$orderby
- [ ] P2 owa-sites: --all/paging on items (silent 50-page cap), $filter/$orderby/$expand, by-id/by-URL addressing, item/file detail by id
- [ ] P2 owa-teams: paging on chats/channels (--top/--all), message send/reply, members command, structured mentions/attachments arrays, --html raw body option
- [ ] P2 owa-ado: --all on prs/runs, wi comment + relation/link mgmt + wi-delete, --api-version escape hatch
- [ ] P2 owa-doctor: broker-reachability + audience-mismatch warning, multi-audience/scope-coverage check, --timeout, repeatable --profile/subset
- [ ] P2 suite-wide: OData passthrough (--select/--filter/--orderby/--expand) where missing (graph/mail/people/todo/planner/sites); config --unset/clear (planner/sites/ado)

## TUI rollout — in flight (master plan: [owa-suite-tui-rollout.md](owa-suite-tui-rollout.md))

  the frozen `BrowserSpec` contract). Both first adapters had to work around
  `actions[key](state)` carrying no `stdscr`: owa-cal copied the kit `_loop`
  into a local `_cal_loop` that drains a `state._pending_respond` sentinel;
  owa-graph fell back to a round-robin `a` instead of a selectable overlay.
  Once landed: drop `_cal_loop`, turn owa-graph's `a` into a real audience
  overlay, and add a pre-fetch redraw hook so the "minting token…" frame paints
  before the blocking owa-piggy mint. (`tui_kit.screen.silence_os_fds()` for
  browser/clipboard launches already landed.)
  schema (`interactive=True`, `explore` alias, `_TUI_FLAGS`) + reject under
  `--agent`/pipe, plus the co-requisite `owa_core/modes.py` `command_name`
  `--profile` guard fix (closes the identical `owa-mail tui` hole). One atomic
  diff. Gate: `tests/graph/test_tui_cli.py` + `tests/core/test_modes.py`. See
  [owa-graph-explorer-tui.md](owa-graph-explorer-tui.md) Phase 3.
  explorer section, version bump (+ `test_version.py`), final adversarial
  review. See [owa-graph-explorer-tui.md](owa-graph-explorer-tui.md) Phase 4.
  owa-ado / owa-planner / owa-teams / owa-sched / owa-doctor — adapters on
  `tui_kit.app`; checklist in [owa-suite-tui-rollout.md](owa-suite-tui-rollout.md).
  --profile` persist already shipped; this is the curses-side switch only)

## Larger plans (standalone files)

- [~] **owa-graph explorer TUI** — interactive curses FOCI-audience explorer.
  Phase 0/1/2 DONE (2026-06-16/17): audiences+seeds, nav engine, auth/token
  cache, and the curses front-end on `tui_kit.app` (graph is the first real
  consumer of the kit's `BrowserSpec` loop). Phase 3/4 remaining — see the TUI
  rollout section above. [owa-graph-explorer-tui.md](owa-graph-explorer-tui.md).
- [ ] **owa-places** — BLOCKED: needs the real `initmeetinglocations` POST body
  captured from browser devtools before scaffolding. [owa-places.md](owa-places.md).

## Done

Completed plans are archived in [done/](done/) and logged in [DONE.md](DONE.md)
(owa-vids merge, owa-teams, owa-shifts closed-as-blocked, owa-mail TUI
overhaul, owa-doctor siblings cross-check, multi-profile fan-out).

- owa-cal TUI (2026-06-17) — agenda browser adapter on `tui_kit.app`
  (`owa-cal tui`): event list + detail + confirm-gated respond, `/` search,
  `--day-range`. Part of the in-flight suite TUI rollout, not a standalone plan.
