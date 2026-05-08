# AGENTS.md

User documentation lives here.

- Examples must use placeholders, `example.com`, or `.invalid` domains.
- Do not include real tenant IDs, profile names from real accounts, tokens, or
  captured Microsoft responses.
- Auth examples must state that `owa-piggy` owns refresh tokens.
- Docs should match `--help`, schema output, and current exit-code behavior.
- Keep security caveats close to auth and token examples.

Nearest tests: `tests/contract/`, `tests/compat/`.

Verify:

```bash
.venv/bin/python -m pytest -q tests/contract tests/compat
.venv/bin/python tools/check_no_secrets.py
```
