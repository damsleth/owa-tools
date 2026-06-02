# Done

Completed plans, newest first. The detailed plan files stay in `.plans/` as
historical record, each with a `Status: DONE` banner pointing back here.

- **owa-mail TUI overhaul** — full-width layout, reading pane, search-400 fix,
  esc overlay menu + persisted settings. Shipped `23b5f21` (2026-06-01),
  `feat(mail): full-width tui with reading pane, esc menu, and settings`.
  Plan: [owa-mail-tui-esc-menu-and-settings.md](owa-mail-tui-esc-menu-and-settings.md).

- **owa-doctor siblings cross-check** — `owa-doctor --json` `siblings[]` entries
  are now asserted schema-compatible with each binary's own `<binary> --doctor
  --json` payload. Shipped `b290aa1` (2026-05-29),
  `test(doctor): cross-check siblings[] against per-binary --doctor schema`.
  Plan: [owa-doctor-siblings-crosscheck.md](owa-doctor-siblings-crosscheck.md).

- **multi-profile fan-out** — repeated `--profile` fans out across profiles via
  the shared `owa_core.modes.run_with_output_modes` entry point (every CLI
  gained it with zero per-tool code; `owa-doctor` opts out). Foundation shipped
  in v0.6.1 (`10cdaff`, 2026-06-02); the post-release follow-up (per-command
  `--help` block, prose docs across `profile-model.md`/README/AGENTS/skill, and
  per-tool end-to-end tests) landed 2026-06-02. Plan now Status: COMPLETE —
  [multi-profile-simultaneous-calls.md](multi-profile-simultaneous-calls.md).
