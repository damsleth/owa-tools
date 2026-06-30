# TODO

> **Priority legend** (suite-wide review, 2026-06-23 — see findings section below)
> - **P0** — correctness / data-loss / contract violations. Do first.
>   The systemic exit-code bug is archived in [done/exit-code-taxonomy-fix.md](done/exit-code-taxonomy-fix.md).
> - **P1** — cheap, agent-facing drift / dead code / misleading help. High value/effort ratio.
> - **P2** — feature gaps (missing params, switches, commands). Schedule per roadmap.
>
> Two findings are large enough to be standalone plans:
> [done/owa-planner-write-support.md](done/owa-planner-write-support.md) (DONE 2026-06-29),
> [done/owa-sched-findmeetingtimes.md](done/owa-sched-findmeetingtimes.md) (DONE 2026-06-30).

## Suite review findings (2026-06-23)

### P0 — correctness / contract
- [x] **exit-code taxonomy collapses to 1** — DONE 2026-06-29: every `api.py` now `raise`s the recoverable OwaError (cal/mail/graph/drive/people/sched/todo/planner/sites/teams already converted; ado raises by design); the central `run_with_output_modes` → `emit_error` returns `int(error.exit_code)`. Fixed the last 4 swallow-and-return-None spots (upload-session paths in owa-mail/owa-drive). Added end-to-end contract test (`test_recoverable_errors_propagate_documented_exit_code`, owa-cal) asserting 10/13/14/15/20 reach the shell. Plan archived to done/. See [done/exit-code-taxonomy-fix.md](done/exit-code-taxonomy-fix.md).
- [x] P0 owa-drive: put --force silently overwrites files >4MiB — RESOLVED earlier: the `_remote_exists` + `--force` preflight (exit 15) gates both the small PUT and the large upload-session path, so no silent overwrite. Per-file fail/replace/rename granularity remains a P2 nice-to-have, not data-loss.
- [x] P0 owa-drive: get --out clobbers existing local file silently — FIXED: refuses with exit 15 unless --force
- [x] P0 owa-ado: PR --repo interpolated unencoded into request path — FIXED: quote(repo, safe='') + build_url keeps '%' safe

### P1 — cheap, agent-facing
- [x] P1 suite-wide cleanup (post exit-code refactor): DONE — deleted the dead `try/except OwaError: raise` wrappers + `_handle_owa_error` (owa-ado/owa-drive), removed unreachable `if x is None: return 1` guards, fixed stale docstrings; hoisted `build_query` into owa_core/query.py (6 importers) and `_require_value` into owa_core.errors (all tools).
- [x] P1 owa-graph: drop stale --app-client-id from config help text — DONE
- [x] P1 owa-sites: positional --site — NO-OP: cmd_site already accepts the bare positional via pop_positional_id (line 139) and the help/schema already say "flag or positional"; regression tests test_site_positional + test_main_routes_site exist. Stale finding.
- [x] P1 owa-people: dead show comment describes email-vs-id branching — DONE: comment corrected (Graph /users accepts both UPN and id at one endpoint, no branching needed)
- [x] P1 owa-cal: wire dead-but-tested normalize_event_detail into a show --id command — DONE (`owa-cal show --id <id>`)
- [x] P1 owa-ado: wire --iteration to build_wiql(iteration=); validate --status — DONE
- [x] P1 owa-teams: rename messages --all → --system-events; add truncation signal at page cap — DONE
- [x] P1 owa umbrella: route meta-commands (list/schema/version) through run_with_output_modes — DONE (meta-commands now honor --agent/--err-json); schema built in-process via importlib import of each tool's COMMAND_SCHEMA, no more 13 subprocesses.

### P2 — feature gaps

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
