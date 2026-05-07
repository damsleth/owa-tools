# Changelog: owa-core

## Unreleased

- Phase 1: Initial public API for `owa_core`.
  - `errors`: `ExitCode` taxonomy, `OwaError` hierarchy, `emit()` with human and JSON output (gated by `OWA_ERR_JSON`/`--err-json`).
  - `tty`: `is_interactive()`, `confirm()` with off-TTY refusal.
  - `jwt`: `decode`, `expires_at`, `scopes`. No signature verification.
  - `config`: atomic key-value store with allowlist, mode `0600`, temp+fsync+rename writes.
  - `dates`: `parse`, `iso_week`, `resolve_tz` (zoneinfo-first, Windows alias table, UTC fallback).
  - `format`: `render`, `pretty_table`, `to_csv`, `to_ndjson`.
  - `http`: `request` with retry-after / 5xx backoff, typed error mapping (401, 403-scope, 404, 409/412, 429, 5xx); `paginate` for `@odata.nextLink`.
  - `auth`: `get_token`, `require_min_piggy`, `verify_identity`. Subprocess bridge to `owa-piggy`.
  - `dispatch`: `Spec`/`Command`/`Arg`/`Flag`, `run` with `--help`, `--help --json`, `schema`/`schema <command>`, `--agent` envelope, `--err-json`, usage-error mapping.
- 39 unit tests under `owa_core/tests/test_phase1.py`.
- Stdlib-only at runtime; `tools/check_stdlib_only.py` passes.
