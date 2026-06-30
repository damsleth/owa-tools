# owa-planner-write-support

> **DONE 2026-06-29** — see [../DONE.md](../DONE.md). All steps shipped:
> `plans.py normalize_*` preserve `@odata.etag` as `etag`; `api.py` has
> `api_post`/`api_patch`/`api_delete` sending `If-Match: <etag>`; `cli.py` has
> `create-task`/`update-task`/`delete-task`/`update-task-details`/
> `update-plan-details` with a `_require_etag` guard and confirm-gated delete;
> 412 stale-etag → `ConflictError` → exit 15 (via the exit-code-taxonomy-fix
> chain), now covered by `test_update_task_stale_etag_propagates_conflict`.

_Created 2026-06-23_

## Goal

Add the mutating half of owa-planner (was read-only). Blocked at plan-time on
ETag/If-Match infrastructure that did not exist.

## Steps (all done)

- [x] `plans.py` `normalize_*` preserve `@odata.etag` as an `etag` field on
      every read shape (plan / bucket / task / detail).
- [x] Add PATCH/POST/DELETE to `api.py`; PATCH/DELETE send `If-Match: <etag>`.
- [x] Re-read the refreshed etag after a write (update-task refreshes).
- [x] 412 Precondition (stale etag) → `ConflictError` → exit 15 propagates
      (depended on [[exit-code-taxonomy-fix]]; tested).
