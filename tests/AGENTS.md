# AGENTS.md

Default tests must be deterministic and offline.

- No real Microsoft network calls.
- No real `owa-piggy` subprocess calls; use fake subprocesses or fake broker
  executables.
- No real tokens, tenant IDs, mailbox data, calendar data, or people data.
- Unit tests live by package under `tests/<tool>/` or `tests/core/`.
- Machine contract tests live in `tests/contract/`.
- Security tests live in `tests/security/`.
- Live tests must be opt-in and skipped by default.

Nearest tests: this directory.

Verify:

```bash
.venv/bin/python -m pytest -q tests
.venv/bin/python tools/check_no_secrets.py
```
