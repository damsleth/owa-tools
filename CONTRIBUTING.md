# Contributing

## Setup

- Python 3.9+. The suite is stdlib-only at runtime, but tooling uses pytest and ruff.
- Install in editable mode for development:
  ```
  pip install -e .[dev]
  ```
- `owa-piggy` must be installed and reachable on PATH.

## Tests

```
pytest                                  # all tests
pytest owa_core/tests                   # core library
pytest tests/compat                     # command-surface snapshots
pytest tests/contract                   # agent contract
OWA_LIVE_TESTS=1 pytest tests/integration  # opt-in live tests
```

## Compatibility snapshots

Before changing a flag, subcommand, default output shape, or documented exit code:

1. Run `python tools/snapshot_cli.py --tool <tool>` to regenerate the affected fixtures.
2. Verify the diff is what you intended.
3. Add a changelog entry in the affected tool's section.
4. Update `docs/agent-integration.md` if the change affects schema.

If the diff includes anything destructive (rename, removal, type change, exit-code reuse), the PR must also bump the tool's `schema` version.

## Stdlib-only check

`tools/check_stdlib_only.py` runs in CI. Allowed runtime imports:

- Python stdlib
- `owa_core`
- The `owa_*` packages in this repo
- `owa-piggy` (subprocess only)

Any other import outside `tests/` and `tools/` fails the build.

## Commit and PR conventions

- One package per PR where practical.
- Commit subject: `<package>: <imperative one-liner>` (e.g., `owa_cal: add --idempotency-key to create`).
- Reference the affected fixture path in the body if you regenerated snapshots.
- Tag releases as `<tool>-vX.Y.Z` (e.g., `owa-cal-v0.6.3`). `owa-core` tags as `owa-core-vX.Y.Z`.

## Code style

- Four-space Python indentation, PEP 8.
- No emoji in source or docs.
- No emdash. Regular dash only.
- Comments only when the why is non-obvious.

## Don't

- Don't add third-party runtime dependencies.
- Don't modify `owa-piggy` from this repo.
- Don't change snapshots without a changelog entry.
- Don't add stderr output to the legacy success path.
