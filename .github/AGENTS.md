# AGENTS.md

GitHub workflows for CI and release automation live here.

- CI must be reproducible locally with commands from root `AGENTS.md`.
- Release workflow builds the root `owa-tools` distribution, not per-tool
  packages.
- Pull requests must never publish artifacts.
- Workflow logs must not print tokens, Authorization headers, or broker output.
- Add checks here only when the corresponding local command exists.

Nearest tests: `src/tests/contract/`, `src/tests/security/`, and packaging smoke tests
when present.

Verify:

```bash
.venv/bin/ruff check .
.venv/bin/python -m pytest -q src/tests/contract tests/security
```
