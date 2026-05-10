# Migrating from individual installs

If you used the legacy per-tool installs (`owa-cal`, `owa-mail`, `owa-graph`,
`owa-doctor`, `owa-people`, `owa-sched`, `owa-drive`) from their old
standalone repositories or Homebrew formulas, this guide walks you through
moving onto the new `owa-tools` suite distribution.

## What changed

- The seven consumer CLIs and the umbrella `owa` discovery binary now ship
  from a single source repository and a single distribution: `owa-tools`.
- All eight binaries share one suite version (`vX.Y.Z`).
- Console binary names are unchanged. Existing scripts, aliases, agent
  prompts, and shell completions keep working.
- `owa-piggy` is unchanged. It is still installed and managed separately,
  it is still the only persistent secret store, and `owa-tools` never
  imports `owa_piggy` Python modules or reads `~/.config/owa-piggy`
  directly. The contract between them is the `owa-piggy` subprocess
  JSON surface.

## Migration paths

### From a pipx / pip install of individual tools

```bash
# Remove the old per-tool installs
pipx uninstall owa-cal
pipx uninstall owa-mail
pipx uninstall owa-graph
pipx uninstall owa-doctor
pipx uninstall owa-people
pipx uninstall owa-sched
pipx uninstall owa-drive

# Install the suite
pipx install owa-tools
```

If you used `pip install --user` instead, run the corresponding
`pip uninstall` for each tool, then `pip install --user owa-tools`.

`owa-piggy` stays as it is. Do not uninstall it.

### From Homebrew

The new tap exposes one suite formula:

```bash
# Replace the old per-tool formulas
brew uninstall owa-cal owa-mail owa-graph owa-doctor owa-people owa-sched owa-drive

# Install the suite
brew install owa-tools
```

For one release cycle, the old per-tool Homebrew formulas remain available
as transitional aliases that point at `owa-tools`. They will be removed
after that cycle, so you should migrate at your earliest convenience. The
deprecation notice on each old formula will name the cycle.

`owa-piggy` keeps its own formula and is unaffected.

### From a development checkout

If you used `pip install -e .` against the old per-tool repos, switch to
an editable install of the monorepo:

```bash
cd path/to/owa-tools
python3 -m venv .venv
.venv/bin/pip install -e .[dev]
```

## Configuration and tokens

Nothing under `~/.config/owa-piggy/` needs to move. Profiles, refresh
tokens, and per-audience caches stay where they are.

Per-tool config files under `~/.config/<tool>/config` are still read by
each tool. The most common entry there is `owa_piggy_profile=<alias>`,
and the precedence rules in `docs/profile-model.md` are unchanged.

## Verification after migration

Run these to confirm the suite is on PATH and healthy:

```bash
owa list
owa doctor --no-tokens
owa-cal --help
owa-mail --help
owa-graph --help
owa-doctor --help
owa-people --help
owa-sched --help
owa-drive --help
```

If credentials are seeded for at least one profile, also run a single
read-only command to confirm the auth path still works end to end. Any
of these is fine:

```bash
owa-piggy whoami --json
owa-graph me
owa-cal list --top 1
owa-mail folders
```

All eight binaries should report the same `owa-tools` suite version:

```bash
owa --version
owa-cal --version
owa-graph --version
```

If `owa list` does not see one of the consumer tools, the most common
cause is a stale shim in `~/.local/bin/` from the old per-tool install.
Remove the orphan and rerun.

## Related docs

- `README.md` for the suite overview.
- `docs/profile-model.md` for how `owa-tools` profile aliases map to
  `owa-piggy` profiles. Profile resolution is unchanged.
- `RELEASING.md` for the suite tag-and-publish flow used to build the
  distribution you just installed.
