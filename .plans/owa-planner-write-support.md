# owa-planner-write-support

_Created 2026-06-23_

## Goal

Add the mutating half of owa-planner (currently read-only by design). Blocked on
ETag/If-Match infrastructure that does not exist yet — this is the architectural
prerequisite, not just new commands.

## Steps

- [ ] **ETag plumbing (do first).** `plans.py` `normalize_*` strips `@odata.etag`; preserve
      it as an `etag` field on read shapes. Add PATCH/POST/DELETE to `api.py` (only
      `api_get` exists today) that send `If-Match: <etag>` and read the refreshed etag
      back from the response. Planner rotates etags on every write.
- [ ] **412 handling** depends on [[exit-code-taxonomy-fix]] — ConflictError must
      surface as exit 15 so callers can re-GET-and-retry on a stale etag.
- [ ] task: create / update / complete / delete; assign / unassign; set due/start/
      priority/progress; move between buckets; order hints.
- [ ] task details: description, checklist items, references (separate `/details` etag).
- [ ] bucket: create / rename / delete. plan: create / delete.
- [ ] Surface `appliedCategories` + resolve label names via `plannerPlanDetails.
      categoryDescriptions` (add a `plan <id>` get command).
- [ ] All mutating commands declare confirmation/idempotency per AGENTS.md.

## Notes

- Read-only v1 is an explicit documented decision (`cli.py:9-11`, `plans.py:9-11`,
  `AGENTS.md:25-28`) — this plan reverses it deliberately.
- Assignee GUID→name resolution is cross-tool with owa-people; defer or wire optionally.

