# TODO

- [ ] optional --pretty renderer for action commands (low priority; only if a human renderer is wanted) — migrated from hugr/.plans
- [ ] add owa-mail functionality for resetting settings to default
- [ ] add owa-mail functionality for switching profiles
- [ ] add owa-mail "all inboxes" view across multiple/all stored profiles
- [x] multi-profile follow-up (post-v0.6.1): per-command --help text for repeatable --profile + exit codes, prose docs (docs/profile-model.md, README, AGENTS, cj-owa-tools skill), and per-tool end-to-end integration tests with mocked auth — DONE 2026-06-02, details in .plans/multi-profile-simultaneous-calls.md (now Status: COMPLETE)

## Larger plans (standalone files)

- [ ] **owa-graph explorer TUI** — interactive curses FOCI-audience explorer for
  owa-graph. Not started; phased multi-agent build spec in
  [owa-graph-explorer-tui.md](owa-graph-explorer-tui.md).
- [ ] **owa-places** — BLOCKED: needs the real `initmeetinglocations` POST body
  captured from browser devtools before scaffolding. [owa-places.md](owa-places.md).
- [ ] **owa-shifts** — BLOCKED by client preauth (`AADSTS65002`); do not build
  until owa-piggy gains a FOCI client-id override or Graph `/schedule` surfaces
  the data. [owa-shifts.md](owa-shifts.md).

## Done

Completed plans are logged in [DONE.md](DONE.md) (owa-mail TUI overhaul,
owa-doctor siblings cross-check, multi-profile fan-out foundation).
