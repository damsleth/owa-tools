# Done

Completed plans, newest first. The detailed plan files move to
[`.plans/done/`](done/) as historical record, each with a status banner
pointing back here.

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
