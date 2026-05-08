# AGENTS.md

Compatibility tests check compatibility with the planned release contract, not
with old internal scaffolding.

- Keep snapshots small and structural.
- Prefer JSON shape assertions over large terminal-output blobs.
- Update snapshots only when the release contract intentionally changes.
- Do not encode live account data.

Nearest tests: `tests/compat/`.

Verify:

```bash
.venv/bin/python -m pytest -q tests/compat
```
