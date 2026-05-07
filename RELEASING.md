# Releasing

Per-tool semver. Tags drive releases.

## Tag format

- Consumer CLIs: `owa-cal-vX.Y.Z`, `owa-mail-vX.Y.Z`, ..., `owa-drive-vX.Y.Z`.
- Shared library: `owa-core-vX.Y.Z`.

The release workflow keys off the tag prefix and publishes only the matching package.

## Pre-release checklist

1. Compatibility snapshots green.
2. Contract tests green.
3. Stdlib-only check green.
4. Changelog updated for the tool (or `CHANGELOG-core.md` for core).
5. Smoke test the wheel in a clean venv.
6. For consumer tools: confirm minimum `owa-piggy` version matches `owa_core.auth.require_min_piggy`.

## owa-core path-dependency to published handoff

During Phase 0-2, `owa-core` is a path dependency consumed in-tree. To release a consumer tool from the monorepo, `owa-core` must be on PyPI first (or vendored in the wheel).

The recommended order:

1. Tag `owa-core-vX.Y.Z` once the API is stable enough for at least two consumers.
2. Wait for the workflow to publish `owa-core` to PyPI.
3. Update each consumer's `pyproject.toml` to pin `owa-core==X.Y.Z` instead of the local path.
4. Run snapshots and contract tests against the pinned version.
5. Tag the consumer release.

Until step 1 happens, consumers cannot ship from the monorepo as wheels. Source-only installs (`pip install -e .`) work fine for development.

If a consumer must release urgently before `owa-core` is on PyPI, bundle `owa-core` into the consumer wheel via `setuptools` `package-data` or a vendored copy. Document the bundle in `CHANGELOG.md`.

## Homebrew

- `owa-tools` formula installs all seven consumer binaries plus the umbrella `owa` binary.
- `owa-piggy` formula stays standalone in the same tap.
- During the cutover, keep the seven legacy per-tool formulas as transitional aliases for one release cycle, then deprecate.

## Backout

If a release introduces a regression:

1. Revert the offending PR on `main`.
2. Tag a patch release with the revert.
3. Yank the affected wheel from PyPI if still in the brief window where that's safe.
4. Document the regression in the changelog.

Do not force-push tags. Do not delete published versions.
