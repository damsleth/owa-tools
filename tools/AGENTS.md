# AGENTS.md

Repository maintenance scripts live here.

- Scripts should be stdlib-only unless they are explicitly dev-only and the
  dependency is already in `[project.optional-dependencies].dev`.
- Prefer fail-closed checks with clear stderr diagnostics and stable exit codes.
- Scripts that enforce release or security policy need tests when nontrivial.
- Do not shell out to live Microsoft services or a real broker in default
  checks.

Nearest tests: `tests/security/`, `tests/contract/`, and script-specific tests.

Verify:

```bash
.venv/bin/ruff check tools tests
.venv/bin/python tools/check_stdlib_only.py
.venv/bin/python tools/check_no_secrets.py
.venv/bin/python tools/check_artifacts.py dist/*
```
