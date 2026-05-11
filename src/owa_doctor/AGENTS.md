# AGENTS.md

`owa_doctor` reports suite, broker, profile, and token health.

- `probe --no-tokens` must work without `owa-piggy` on PATH.
- Health exit codes are command-specific and must stay documented.
- JSON report shape is a contract consumed by `owa doctor`.
- Never print token values. Status may report presence and expiry metadata only.
- Docs live in `docs/doctor.md`.

Nearest tests: `src/tests/doctor/`, `src/tests/contract/`.

Verify:

```bash
.venv/bin/ruff check src/owa_doctor src/tests/doctor
.venv/bin/python -m pytest -q src/tests/doctor tests/contract
```
