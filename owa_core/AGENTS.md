# AGENTS.md

`owa_core` contains shared contracts used by every consumer CLI.

- Keep this package domain-neutral. Microsoft resource behavior belongs in a
  tool package.
- Runtime imports remain stdlib-only.
- Expected failures use `owa_core.errors`; new shared HTTP paths use
  `owa_core.http`; new shared auth paths use `owa_core.auth`.
- Do not call `sys.exit()` here. Raise typed errors and let CLIs decide how to
  render or exit.
- Do not print except in explicit render/debug helpers.
- Redact tokens and sensitive response bodies with `owa_core.secrets`.

Nearest tests: `tests/core/`, `tests/security/`.

Verify:

```bash
.venv/bin/ruff check owa_core tests/core tests/security
.venv/bin/python -m pytest -q tests/core tests/security
```
