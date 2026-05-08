# AGENTS.md

`owa_doctor` reports suite, broker, profile, and token health.

- `probe --no-tokens` must work without `owa-piggy` on PATH.
- Health exit codes are command-specific and must stay documented.
- JSON report shape is a contract consumed by `owa doctor`.
- Never print token values. Status may report presence and expiry metadata only.
- Docs live in `docs/doctor.md`.

Nearest tests: `tests/doctor/`, `tests/contract/`.

Verify:

```bash
.venv/bin/ruff check owa_doctor tests/doctor
.venv/bin/python -m pytest -q tests/doctor tests/contract
```
