# Releasing

Suite semver. Tags drive releases.

## Tag format

- `vX.Y.Z`

The release workflow builds the root `owa-tools` package. It contains the umbrella binary plus all consumer CLIs.

## Pre-release checklist

1. `pytest -q --cov=owa_core --cov-fail-under=95` green.
2. `python tools/check_stdlib_only.py`, `python tools/check_no_secrets.py`,
   and `python tools/check_docs_sync.py` green.
3. `python -m build`, `python -m twine check dist/*`, and
   `python tools/check_artifacts.py dist/*` green.
4. `python tools/check_console_smoke.py` green.
5. Changelog updated for the suite version.

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
