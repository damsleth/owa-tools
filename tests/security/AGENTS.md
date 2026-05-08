# AGENTS.md

Security tests enforce the suite boundary and fake-token policy.

- Build token-shaped values at runtime in tests; do not commit literal
  secret-looking strings.
- Redaction tests must prove access-token, refresh-token, Authorization header,
  and client-secret shapes are removed.
- Artifact tests must reject caches, virtualenvs, config files, and `.plans`
  from distributions.
- No real tenant IDs, profile aliases from real accounts, or captured Microsoft
  responses.

Nearest tests: `tests/security/`.

Verify:

```bash
.venv/bin/python -m pytest -q tests/security
.venv/bin/python tools/check_no_secrets.py
```
