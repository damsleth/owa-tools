# Releasing

Per-tool semver. Tags drive releases.

## Tag format

- Consumer CLIs: `owa-cal-vX.Y.Z`, `owa-mail-vX.Y.Z`, ..., `owa-drive-vX.Y.Z`.

The release workflow keys off the tag prefix and publishes only the matching package.

## Pre-release checklist

1. `pytest -q` green.
2. `python tools/check_stdlib_only.py` green.
3. Changelog updated for the tool.
4. Smoke test the wheel in a clean venv.

## Homebrew

- `owa-tools` formula installs all seven consumer binaries plus the umbrella `owa` binary.
- `owa-piggy` formula stays standalone in the same tap.

## Backout

If a release introduces a regression:

1. Revert the offending PR on `main`.
2. Tag a patch release with the revert.
3. Yank the affected wheel from PyPI if still in the brief window where that's safe.
4. Document the regression in the changelog.

Do not force-push tags. Do not delete published versions.
