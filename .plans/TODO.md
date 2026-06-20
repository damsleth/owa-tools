# TODO

- [ ] optional --pretty renderer for action commands (low priority; only if a human renderer is wanted)

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
