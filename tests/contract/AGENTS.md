# AGENTS.md

Contract tests define the release API for scripts and agents.

- Assert stdout, stderr, exit codes, and JSON shape.
- Schema, help, and version behavior are release contracts.
- Snapshot changes must be intentional and reviewed with the command surface.
- Do not hit the real broker or Microsoft services.

Nearest tests: `tests/contract/`.

Verify:

```bash
.venv/bin/python -m pytest -q tests/contract
```
