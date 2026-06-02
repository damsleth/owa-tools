# Contributing

## Setup

- Python 3.10+. The suite is stdlib-only at runtime, but tooling uses pytest and ruff.
- Install in editable mode for development:
  ```
  pip install -e .[dev]
  ```
- `owa-piggy` must be installed and reachable on PATH.

## Tests

```
pytest                                # all tests
pytest src/tests/cal                  # one tool
python src/scripts/check_no_secrets.py      # secret-shape scanner
```

Coverage gates (matching CI):

```
coverage run --source=owa_core -m pytest -q
coverage report --fail-under=95
pytest -q --cov --cov-fail-under=90
```

The first enforces 95%+ on `owa_core` only; the second enforces 90%+ across
the full runtime surface configured in `pyproject.toml`.

## Build and packaging checks

After `uv build`, verify the artifacts:

```
python src/scripts/check_artifacts.py dist/*
python src/scripts/check_console_smoke.py
```

`check_console_smoke.py` installs the wheel into a throwaway venv and runs
`--version` on every console script, so it catches packaging regressions
before they reach a tag.

Before editing, read root `AGENTS.md` and the nearest local `AGENTS.md`.

## Stdlib-only check

`src/scripts/check_stdlib_only.py` runs in CI. Allowed runtime imports:

- Python stdlib
- The `owa_*` packages in this repo
- `owa-piggy` (subprocess only)

Any other import outside `src/tests/` and `src/scripts/` fails the build.

## Commit and PR conventions

- One package per PR where practical.
- Commit subject: `<package>: <imperative one-liner>` (e.g., `owa_cal: add --idempotency-key to create`).
- Tag suite releases as `vX.Y.Z`.

## Code style

- Two-space indentation in shell and docs; four-space Python indentation, PEP 8.
- No emoji in source or docs.
- No emdash. Regular dash only.
- Comments only when the why is non-obvious.

## Don't

- Don't add third-party runtime dependencies.
- Don't read `owa-piggy` config directly or import `owa_piggy`.

## Deeper reference

- [`docs/architecture.md`](docs/architecture.md) - low-entropy architecture,
  the shared `owa_core` contract layer, and maintainability constraints.
- [`docs/testing.md`](docs/testing.md) - the test layers, what each is for, and
  the coverage gates.
- [`docs/new-tool-onboarding.md`](docs/new-tool-onboarding.md) - the process for
  landing a new companion CLI.
- [`docs/security.md`](docs/security.md) - the broker boundary, threat model,
  and redaction rules.
