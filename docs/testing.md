# Testing and Coverage

How the `owa-tools` test suite is laid out, what each layer is for, and the
gates CI enforces. Read this before adding or restructuring tests so new tests
land in the right layer with the right fixtures.

The guiding principle: behavior is specified by tests before users install the
suite. Coverage is broad where contracts matter and focused where live
Microsoft behavior would make tests brittle.

## Where tests live

Tests live under `src/tests/`:

- `src/tests/core/` - pure unit tests for `owa_core` (`test_http.py`,
  `test_auth.py`, `test_version.py`, `test_conventions.py`, `test_modes.py`,
  `test_upload.py`, ...). The "HTTP mapping" and "fake broker" layers live here.
- `src/tests/<tool>/` - one directory per tool (`cal`, `mail`, `graph`,
  `doctor`, `people`, `sched`, `drive`, `todo`), each with a `conftest.py` that
  fakes the broker / token path, plus `test_cli.py`, `test_format.py`,
  `test_models.py`, etc.
- `src/tests/contract/` - cross-suite CLI contract tests
  (`test_suite_contract.py`): help / version / schema / exit-code surface for
  every binary.
- `src/tests/compat/` - compatibility-with-release-contract snapshots.
- `src/tests/security/` - redaction, secret-fixture, and packaging artifact
  tests (`test_artifacts.py`, `test_secrets.py`, `test_config_permissions.py`,
  `test_emit_token_leak.py`).
- `src/tests/docs/` - docs-sync / examples tests.
- `src/tests/<tool>/test_live.py` - opt-in live smoke, per tool (not a central
  `live/` directory).

Maintenance scripts that back the security and packaging layers live under
`src/scripts/`: `check_stdlib_only.py`, `check_no_secrets.py`,
`check_docs_sync.py`, `check_artifacts.py`, `check_console_smoke.py`.

## Test layers

### 1. Pure unit tests (`src/tests/core/`, `src/tests/<tool>/`)

Target: `owa_core.{errors,http,auth,config,dispatch,schema,tty,secrets}`,
per-tool payload/path builders, normalizers, date/timezone helpers.

Assertions: no network; no subprocess unless explicitly faked; no writes
outside `tmp_path`; stable return values; precise error types and exit codes.

### 2. CLI contract tests (`src/tests/contract/`)

Every binary, exercised against the editable install:

- `--help`, `--help --json`, `--version`, `schema`, `schema <command>`
- unknown command exits `2`; unknown flag exits `2`; missing flag value exits `2`
- `--err-json` / `OWA_ERR_JSON=1` emit structured JSON on stderr
- `--agent` / `OWA_AGENT=1` wrap success output where applicable
- successful JSON commands keep stderr empty unless in debug / human mode

### 3. Compatibility-with-contract snapshots (`src/tests/compat/`)

Snapshot help-text shape, JSON help schema, command schema, and
stdout/stderr/exit for representative commands as small JSON shape fixtures
(not golden terminal blobs). Includes destructive-command non-TTY refusal.

### 4. Fake broker (per-tool `conftest.py` + `src/tests/core/test_auth.py`)

The broker is faked at the token boundary, not via a fake executable on PATH.
Scenarios covered: good / old `--version`, good `token --json`, token JSON
missing `access_token`, refresh-token rejected / redacted, non-JSON output,
auth-expired stderr, timeout, broker missing. No `owa-tools` test needs the
real broker in CI.

### 5. HTTP mapping (`src/tests/core/test_http.py`)

Monkeypatched `urllib.request.urlopen`. Status mapping (200 / 204 / raw /
invalid-JSON / 401 / 403 / 404 / 409 / 412 / 429+retry-after / 429-over-cap /
503 / URLError), pagination via `@odata.nextLink`, max-pages truncation.
Asserts typed errors and no token leakage in error strings.

### 6. Security (`src/tests/security/`)

Redaction of JWT-looking access tokens and FOCI refresh-token shapes; no
fixture carries token-shaped values except explicit fakes; config files `0600`
and directories `0700` on POSIX; wheel / sdist exclude caches, venvs, pyc,
local config; debug logs redact Authorization; broker output redacted before
rendering; `--curl` / `--az` rendered commands carry no live token by default.

### 7. Packaging (`src/scripts/check_artifacts.py`, `check_console_smoke.py`, `src/tests/security/test_artifacts.py`)

After build: fresh-venv install, then `owa version|list|schema`, every
`<tool> --help|--version|schema`, `owa-doctor probe --no-tokens`, and a wheel
file-list inspection.

### 8. Live (`src/tests/<tool>/test_live.py`)

Never run by default. Gated on `OWA_LIVE_TESTS=1` plus an explicit
`OWA_PROFILE`. Read-only smoke (`owa-piggy token --json --audience graph`,
`owa-graph GET /me`, `owa-cal events --limit 1`, etc.). Skips with a clear
reason when scopes are unavailable.

## Coverage gates

Configured in `pyproject.toml` with `branch = true` and `fail_under = 89` over
the nine runtime packages (currently ~89.4% line+branch).

```toml
[tool.coverage.run]
branch = true
source = ["owa", "owa_core", "owa_cal", "owa_mail", "owa_graph", "owa_doctor", "owa_people", "owa_sched", "owa_drive", "owa_todo"]

[tool.coverage.report]
fail_under = 89
show_missing = true
skip_covered = true
```

The aspirational targets are a ratchet, not a release blocker: total `>=90%`,
`owa_core >=95%`, branch `>=85%` on the core contract modules, per-tool
`>=85%`. The weakest current spots are `owa_todo` (newest tool) and parts of
`owa_people` / `owa_sched`. Ratchet `fail_under` upward as those fill in; do
not block maintenance work on hitting 90/95.

## Test data policy

Fake tokens only (`fake-access-token`, `fake-refresh-token`, synthetic JWTs
generated in tests). No real tenant IDs. Email addresses only from example
domains (`user@example.com`, `a@example.invalid`). No captured Microsoft
responses unless scrubbed to minimum shape.

## CI (`.github/workflows/ci.yml`)

One `test` job over the 3.10 / 3.11 / 3.12 matrix: `ruff check .`, install,
`pytest -q --cov --cov-fail-under=89`, `python -m build`, then
`python src/scripts/check_console_smoke.py`. `release.yml` mirrors the same
gates on tag push before building and publishing.

## Local acceptance commands

```sh
ruff check .
ruff format --check .
python src/scripts/check_stdlib_only.py
python src/scripts/check_no_secrets.py
python src/scripts/check_docs_sync.py
pytest -q --cov
python -m build && python src/scripts/check_artifacts.py dist/*
python src/scripts/check_console_smoke.py
```
