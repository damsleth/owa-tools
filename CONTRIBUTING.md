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
pytest                                # all tests
pytest tests/cal                      # one tool
```

## Stdlib-only check

`tools/check_stdlib_only.py` runs in CI. Allowed runtime imports:

- Python stdlib
- The `owa_*` packages in this repo
- `owa-piggy` (subprocess only)

Any other import outside `tests/` and `tools/` fails the build.

## Commit and PR conventions

- One package per PR where practical.
- Commit subject: `<package>: <imperative one-liner>` (e.g., `owa_cal: add --idempotency-key to create`).
- Tag releases as `<tool>-vX.Y.Z` (e.g., `owa-cal-v0.6.3`).

## Code style

- Two-space indentation in shell and docs; four-space Python indentation, PEP 8.
- No emoji in source or docs.
- No emdash. Regular dash only.
- Comments only when the why is non-obvious.

## Don't

- Don't add third-party runtime dependencies.
- Don't modify `owa-piggy` from this repo.
