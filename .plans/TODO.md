# TODO

- [ ] optional --pretty renderer for action commands (low priority; only if a human renderer is wanted) — migrated from hugr/.plans
- [ ] add owa-mail functionality for resetting settings to default
- [ ] add owa-mail functionality for switching profiles
- [ ] add owa-mail "all inboxes" view across multiple/all stored profiles
- [ ] owa-teams `messages --since <iso>` — stop following `backwardLink` past the cutoff (closes yaams' cold-start history gap)
- [ ] owa-teams `messages --region <emea|amer|…>` — per-call region override so multi-region profiles don't depend on single-valued config

## Larger plans (standalone files)

- [ ] **owa-graph explorer TUI** — interactive curses FOCI-audience explorer for
  owa-graph. Not started; phased multi-agent build spec in
  [owa-graph-explorer-tui.md](owa-graph-explorer-tui.md).
- [ ] **owa-places** — BLOCKED: needs the real `initmeetinglocations` POST body
  captured from browser devtools before scaffolding. [owa-places.md](owa-places.md).

## Done

Completed plans are archived in [done/](done/) and logged in [DONE.md](DONE.md)
(owa-vids merge, owa-teams, owa-shifts closed-as-blocked, owa-mail TUI
overhaul, owa-doctor siblings cross-check, multi-profile fan-out).
