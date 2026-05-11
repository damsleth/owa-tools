# AGENTS.md

User documentation lives here.

- Examples must use placeholders, `example.com`, or `.invalid` domains.
- Do not include real tenant IDs, profile names from real accounts, tokens, or
  captured Microsoft responses.
- Auth examples must state that `owa-piggy` owns refresh tokens.
- Docs should match `--help`, schema output, and current exit-code behavior.
- Keep security caveats close to auth and token examples.
- Update `docs/security.md` when token, config, redaction, or live-test
  boundaries change.
- Update `docs/agent-integration.md` when schema, `--agent`, `--err-json`, or
  exit-code behavior changes.

Nearest tests: `src/tests/contract/`, `src/tests/compat/`.

Verify:

```bash
.venv/bin/python -m pytest -q src/tests/contract src/tests/compat
.venv/bin/python src/scripts/check_no_secrets.py
.venv/bin/python src/scripts/check_docs_sync.py
```
