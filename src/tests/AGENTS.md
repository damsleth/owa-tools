# AGENTS.md

Default tests must be deterministic and offline.

- No real Microsoft network calls.
- No real `owa-piggy` subprocess calls; use fake subprocesses or fake broker
  executables.
- No real tokens, tenant IDs, mailbox data, calendar data, or people data.
- Unit tests live by package under `src/tests/<tool>/` or `src/tests/core/`.
- Machine contract tests live in `src/tests/contract/`.
- Security tests live in `src/tests/security/`.
- Live tests must be opt-in and skipped by default.

See `docs/testing.md` for the full layer map (which layer a new test belongs in
and what each one fakes), the test-data policy, and the coverage gates.

Nearest tests: this directory.

Verify:

```bash
.venv/bin/python -m pytest -q tests
.venv/bin/python src/scripts/check_no_secrets.py
```
