# AGENTS.md

`owa_planner` handles Microsoft Planner (plans / buckets / tasks) over the
Microsoft Graph `/planner` surface.

- Auth audience is `graph` (`https://graph.microsoft.com/v1.0`). The OWA SPA
  token carries **no `Tasks.*` scope**, yet Planner reads work: they are gated
  on `Group.ReadWrite.All`, which the token has. Verified live 2026-06-01 -
  `GET /me/planner/plans` and `GET /groups/{id}/planner/plans` both return 200.
  Do NOT add a `Tasks.*` gate; it would wrongly reject a working token.
- Planner ≠ To Do. Different API, different data model (plans/buckets/
  assignments vs. To Do lists/tasks). `owa_todo` is the To Do tool; keep them
  separate. The internal `tasks.teams.microsoft.com` / `project.microsoft.com`
  APIs are NOT usable here - they return AADSTS65002 (the One Outlook Web client
  is not preauthorized for those resources, and they are not FOCI members).
- Wire format is camelCase; `plans.py` normalizes to a stable lowercase shape.
  Date fields (dueDateTime, startDateTime, completedDateTime, createdDateTime)
  are ISO-8601 UTC; `_local_date` surfaces the local `YYYY-MM-DD`.
- Status is derived from `percentComplete` (0 / 1-99 / 100 -> NotStarted /
  InProgress / Completed); priority int -> label via Microsoft's 0-1/2-4/5-7/
  8-10 = urgent/important/medium/low mapping.
- `task` merges `planner/tasks/{id}` with `planner/tasks/{id}/details`
  (description + checklist + references) - details is a separate GET, fetched
  only for the single-task view, not list views.
- **Read-only v1.** Writes are deferred: Planner PATCH requires the exact
  `@odata.etag` in an `If-Match` header and the etag rotates on every write, so
  a write phase needs GET-then-PATCH + confirmation gating. Assignee GUID->name
  resolution is also deferred (cross-tool with owa-people); v1 surfaces GUIDs.
- Docs live in `docs/planner.md`.

Nearest tests: `src/tests/planner/`.

Verify:

```bash
.venv/bin/ruff check src/owa_planner src/tests/planner
.venv/bin/python -m pytest -q src/tests/planner
```
