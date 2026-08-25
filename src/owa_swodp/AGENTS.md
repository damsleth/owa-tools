# AGENTS.md

`owa_swodp` owns ServiceNow SWODP timesheet access through a dedicated Edge
sidecar profile. It does not use or import `owa-piggy`.

- Prod and UAT use separate profile directories.
- Cookies and `window.g_ck` stay in memory and must never be printed or written.
- `time_card` failures are fatal; `resource_allocation` 403s degrade gracefully.
- Only Pending cards may be changed. Description creation is POST without
  `comments`, then PATCH, then GET verification.
- `submit`/`delete` act on one Pending card by `sys_id`. `recall` acts on one
  Submitted card and requires a non-empty reason. State transitions use the
  `timecardprocessor.do` portal processor (form-encoded, no `result` envelope),
  not the Table API; reads and deletes use the Table API.
- Recall sends `new_state=Recalled` plus `reason`, then verifies that the card
  reached `Recalled`. Recalled cards are editable again in the portal. The live
  portal wire contract is confirmed; the CLI's Submit-then-Recall cycle remains
  offline-verified until a legitimate Pending production card is available.
- Description is mandatory on `time_card`; a blank one blocks timesheet
  submission in the portal. Write rows must carry a non-empty `description`
  unless they are `remove` rows.
- Live writes go to UAT where an instance exists. Production-only verification
  needs explicit operator authorization plus snapshot, one row, verify, restore.
- Never gate a decision on a read passed through an output-filtering proxy; it
  can drop rows and rewrite states. Verify with the bare binary.

Nearest tests: `src/tests/swodp/`.

```bash
.venv/bin/ruff check src/owa_swodp src/tests/swodp
.venv/bin/python -m pytest -q src/tests/swodp
```
