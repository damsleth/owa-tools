# AGENTS.md

`owa_swodp` owns ServiceNow SWODP timesheet access through a dedicated Edge
sidecar profile. It does not use or import `owa-piggy`.

- Prod and UAT use separate profile directories.
- Cookies and `window.g_ck` stay in memory and must never be printed or written.
- `time_card` failures are fatal; `resource_allocation` 403s degrade gracefully.
- Only Pending cards may be changed. Description creation is POST without
  `comments`, then PATCH, then GET verification.
- Live writes go to UAT where an instance exists. Production-only verification
  needs explicit operator authorization plus snapshot, one row, verify, restore.
- Never gate a decision on a read passed through an output-filtering proxy; it
  can drop rows and rewrite states. Verify with the bare binary.

Nearest tests: `src/tests/swodp/`.

```bash
.venv/bin/ruff check src/owa_swodp src/tests/swodp
.venv/bin/python -m pytest -q src/tests/swodp
```
