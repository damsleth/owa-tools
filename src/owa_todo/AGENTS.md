# AGENTS.md

`owa_todo` handles Microsoft To Do tasks over the Outlook REST v2.0 Tasks API.

- Auth audience is `outlook` (NOT graph): the OWA SPA token carries
  `Tasks.ReadWrite` on the outlook.office.com resource but not on graph.
  Endpoints live under `https://outlook.office.com/api/v2.0/me/taskfolders`
  and `.../me/tasks`. Same audience, base, and `api_request`/`paginate_all`
  helpers as `owa_cal`.
- Wire format is PascalCase; `tasks.py` normalizes to lowercase keys on read
  and emits PascalCase on write. Task date fields (DueDateTime, StartDateTime,
  CompletedDateTime, ReminderDateTime) are UTC, so `to_local` treats naive
  datetimes as UTC. We deliberately do NOT carry owa_cal's full Windows-zone
  table here; if To Do ever returns named Windows zones for tasks, promote
  `owa_cal.events.to_local` into `owa_core` rather than copying it.
- Completion is `PATCH {Status: "Completed"}` (the `done` command); the server
  sets CompletedDateTime. `delete` is destructive and confirmation-gated like
  `owa_cal delete`.
- `--folder` accepts a folder name or Id; names resolve via `me/taskfolders`.
- The live To Do web app uses the `substrate.office.com/todob2/api/v1` API
  (camelCase-ish, `Value`/`DeltaLink` delta sync). We target the documented
  Outlook REST v2.0 path instead: it works on the existing `outlook` token,
  uses standard OData (`value`/`@odata.nextLink`), and mirrors owa_cal. If
  Microsoft retires the v2.0 Tasks API, migrate to todob2 (needs custom
  delta-link pagination).
- Per-profile Conditional Access can withhold Tasks scope (e.g. a strict
  tenant): calls then exit 12 (ScopeInsufficient), handled by the shared path.
- Docs live in `docs/todo.md`.

Nearest tests: `src/tests/todo/`.

Verify:

```bash
.venv/bin/ruff check src/owa_todo src/tests/todo
.venv/bin/python -m pytest -q src/tests/todo
```
