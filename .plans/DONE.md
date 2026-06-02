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
  per-tool end-to-end tests) shipped in **v0.6.2** (`c81f27e`, 2026-06-02) —
  commits `9316e7f` (docs), `22097d3` (tests), `ad684fe` (plans housekeeping).
  Plan Status: COMPLETE —
  [multi-profile-simultaneous-calls.md](multi-profile-simultaneous-calls.md).

  **Released v0.6.2 (2026-06-02), all channels:** tag `v0.6.2` + GitHub Release
  (CI workflow green, wheel + sdist attached); PyPI
  [`owa-tools 0.6.2`](https://pypi.org/project/owa-tools/0.6.2/) (wheel + sdist);
  Homebrew tap `damsleth/homebrew-tap` bumped 0.5.0 → 0.6.2
  (`Formula/owa-tools.rb`, GitHub source archive). cj-owa-tools skill updated in
  `skills-private`. (Patch bump: docs + tests over already-shipped behaviour.)
