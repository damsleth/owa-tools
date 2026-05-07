# Migrating from individual installs

If you previously installed the consumer tools individually:

```bash
brew install damsleth/tap/owa-cal
brew install damsleth/tap/owa-mail
brew install damsleth/tap/owa-graph
# ...
```

you can switch to the consolidated `owa-tools` distribution. All seven tools, plus the umbrella `owa` binary, now ship together.

## What stays the same

- All binary names. `owa-cal`, `owa-mail`, `owa-graph`, `owa-doctor`, `owa-people`, `owa-sched`, `owa-drive` work exactly as before.
- All command surfaces. Every documented subcommand, flag, and JSON output shape is preserved.
- All config files. `~/.config/owa-cal/config`, `~/.config/owa-mail/config`, etc. are read in place.
- `owa-piggy` stays separate. It owns the refresh-token threat model and remains its own brew formula.

## What changes

- One install command instead of seven.
- Per-tool versions advance independently; the suite ships as one unit.
- A new umbrella `owa` binary lands on PATH. Use it for discovery (`owa list`, `owa schema`) and as a thin shortcut to `owa-doctor probe`.
- New optional agent contract: `--agent`, `--err-json`, `<tool> schema`. Existing pipelines are unaffected unless you opt in.

## Migration paths

### Homebrew

```bash
# Add the tap (already present if you had any consumer tool installed).
brew tap damsleth/tap

# Install the consolidated suite. Existing per-tool formulas remain as
# transitional aliases for one release cycle.
brew install damsleth/tap/owa-tools

# Once owa-tools is verified locally, uninstall the per-tool formulas.
# Order doesn't matter; they share no state with owa-tools beyond
# ~/.config/owa-*/.
brew uninstall owa-cal owa-mail owa-graph owa-doctor owa-people owa-sched owa-drive
```

### pipx

```bash
# Remove old per-tool installs.
pipx uninstall owa-cal owa-mail owa-graph owa-doctor owa-people owa-sched owa-drive

# Install the bundle.
pipx install owa-tools
```

### pip (developer install)

```bash
git clone https://github.com/damsleth/owa-tools
cd owa-tools
pip install -e .
```

## Verification

```bash
owa list             # JSON listing every installed consumer
owa version          # umbrella version
owa-cal --help       # any consumer still works
owa-piggy whoami     # auth still flows through owa-piggy
```

## Rollback

If you need to roll back during the transitional release:

```bash
brew uninstall owa-tools
brew install damsleth/tap/owa-cal damsleth/tap/owa-mail # ...
```

The per-tool formulas are kept as deprecated aliases for one release cycle so rollback is a one-step command.

## What's gone

Nothing. The migration is additive. The only delete is the duplicate `auth.py`/`jwt.py`/`config.py`/`dates.py`/`format.py` modules in each per-tool repo, which is internal cleanup with no user-visible effect.
