# owa-tools code review — 2026-09-08

Completed against local HEAD `3d4336f`, suite 1.5.2. Initial tracked working tree clean.
Source review and all probes were offline; no Microsoft calls, real broker calls,
production mutations, sibling-repository changes, commits, or releases were requested or performed.
Only `.plans/` was edited. Runtime fixes below are pending.

## Findings, ordered by impact

Review priorities: P1 = high-impact correctness/data-loss/privacy issue; P2 = other
correctness or automation-contract defect. IDs are stable and correspond to
[the executable probes](reproduce.py) and [their results](reproductions.txt).
Probes assert the defective behavior on this checkout; they are evidence, not
regression tests to copy unchanged when fixing the code.

### R1 — P1: Drive overwrites after an inconclusive existence check

`src/owa_drive/cli.py:261,360-369`; `src/owa_drive/api.py:91`.
`_remote_exists` converts every OwaError except NotFoundError into `None`.
`cmd_put` refuses only `exists is True`, so a network/auth/scope/rate-limit error
allows upload without `--force`. The large-file path explicitly requests
`conflictBehavior=replace`; the small-file path has no conditional-create guard.
The probe injects NetworkError in the real preflight and observes `_upload_one`
being called and success returned. The old TODO's “RESOLVED” claim is unsafe.

Fix: treat only a confirmed 404 as absent; propagate other errors. Enforce
no-overwrite at the server as well, so creation between GET and PUT cannot race
the guard. Test both upload sizes, failed preflights, and a concurrent create.

### R11 — P1: SWODP split removes originals before validating replacements

`src/owa_swodp/service.py:494-511`.
The split loop calls `delete_pending` before `_project_base` resolves the task.
If task resolution fails or returns no task, existing Pending cards have already
been deleted and no replacement is created. An API failure while creating later
rows has the same destructive ordering risk. The probe proves the exact sequence
GET cards → DELETE original → GET nonexistent task, ending with deleted/skipped.

Fix: validate all replacement identities and required lookups before any delete.
Design explicit recoverable partial-progress handling for replacement failures;
retain IDs and original content in the operation result. Test missing tasks,
lookup errors, creation errors, and failures halfway through a split. Do this
offline; this review is not permission to exercise production writes.

### R5 — P1: Multi-profile errors bypass redaction

`src/owa_core/modes.py:375-377,430-448`.
Unlike `emit_error`, fan-out stores `error.message` directly and prints it in
JSON, NDJSON, and pretty output. An OwaError containing a response body or secret
therefore bypasses the shared redactor. A synthetic token-shaped string survives
in both profile error records in the probe.

Fix: redact once at the error-record boundary, before every renderer. Test all
three output modes, including JWTs and message-content fields. Preserve the
per-profile typed exit code and useful diagnostics.

### R4 — P1: Escaped quotes leak message content through the body redactor

`src/owa_core/secrets.py:30-32,86`.
`BODY_FIELD_RE` stops at any quote, including an escaped quote inside a JSON
string. With Content containing `hello "PRIVATE_REMAINDER"`, the suffix remains
in the supposedly scrubbed result. This reaches normal HTTP debug body logging.

Fix: redact parsed structured values or use a string matcher that handles JSON
escapes correctly. Test escaped quotes, backslashes, newlines, nested bodies,
case variants, and malformed/truncated error text. Do not weaken token redaction.

### R9 — P1: HTTP debug exposes signed upload capabilities

`src/owa_core/http.py:130,210`; reached from `owa_core.upload.upload_session`.
Both HTTP helpers print the URL verbatim. The unauthenticated upload path uses a
preauthorized upload URL, so debug logging exposes its credential-bearing query.
The offline probe shows a synthetic `sig` value printed unchanged. Applying the
current JWT-shaped redactor alone would not protect opaque signatures.

Fix: use a shared safe URL formatter that removes sensitive query values (or the
query entirely) for logging. Test both HTTP helpers and an upload-session caller
with opaque signed URLs and token query parameters.

### R2 — P1: Availability JSON crashes on normal working-hours data

`src/owa_sched/schedule.py:45,69`; `src/owa_sched/cli.py:319`.
`normalize_attendee` puts a set of weekday integers and datetime.time instances
inside `workingHours`. `cmd_availability` passes the result to `json.dumps`,
which raises TypeError. Shared dispatch does not convert that exception into a
typed error. The probe uses the real CLI handler and a mocked getSchedule payload
with ordinary workingHours; it fails with “not JSON serializable”.

Fix: keep normalized output JSON-safe and convert to internal time/set objects
only inside the slot calculation. Test default JSON, --agent and fan-out with
nonempty workingHours, not only fixtures where the field is absent.

### R3 — P1: Failed attendee lookups become successful free-time suggestions

`src/owa_sched/schedule.py:72-80,124`; `src/owa_sched/cli.py:438-465`.
An attendee error yields an empty busy list. `find_open_slots` ignores `error`,
so `find-time` treats an inaccessible mailbox as completely free and prints
candidate slots with exit 0. The CLI probe returns normal slots even though the
only attendee failed lookup.

Fix: distinguish unknown availability from free availability. Refuse to claim
common free time when a requested participant failed, or return an explicit
partial/unknown result that cannot be mistaken for a valid recommendation.
Test one failed attendee, mixed successful/failed attendees, and malformed busy
intervals (currently silently discarded).

### R7 — P2: Binary safety checks can be bypassed by aliases and argument order

`src/owa_drive/cli.py:675`; `src/owa_core/modes.py:171-184`.
Only `get` is registered as binary; `download` is resolved later in the tool.
`owa-drive download /fake --agent` reaches binary writing while stdout is a
StringIO and raises AttributeError on `.buffer`. Also, shared `command_name`
treats a leading profile value as the command (`--profile work get ...`).
This affects guards and command metadata. Fan-out can encounter the same alias
problem. Umbrella dispatch deserves the same regression coverage.

Fix: determine the canonical command after parsing global option values and
aliases, before guard checks or authentication. Test get/download, profiles before
and after the command, multi-profile mode, --out, and umbrella invocation.

### R8 — P2: Transport timeouts escape the documented network-error contract

`src/owa_core/http.py:174,247`.
The helpers catch URLError but not a direct TimeoutError from opening or reading
the response. Shared CLI dispatch catches only OwaError/SystemExit. The probe
injects TimeoutError into the HTTP transport and observes it escape unchanged;
users get a traceback/exit 1 instead of network exit 10 and structured stderr.

Fix: translate expected socket/time-out/read failures to NetworkError, preserving
the cause and redaction. Test both helpers, connection failure and mid-body read
failure; avoid converting programming errors indiscriminately.

### R6 — P2: Fan-out reports failed records while returning success

`src/owa_core/modes.py:396,419-427`.
When a successful dispatcher emits non-JSON text, `_emit_multi_json` produces an
`ok:false` record with `exit_code:0`. `_multi_exit_code` still sees the original
successful records, returning 0 even when every emitted result failed. Existing
text-producing commands such as help/version can reach this path.

Fix: validate/normalize captured output before both rendering and aggregate exit
selection. Test all-invalid and mixed valid/invalid outputs and ensure result
exit codes agree with the outer exit code.

### R10 — P2: Teams page caps silently report incomplete collections as complete

`src/owa_teams/api.py:76-86`; `src/owa_core/http.py:286-287`.
`graph_collect` promises to signal either item or page truncation. It receives
items from a paginator that simply stops at max_pages, then returns
`truncated=False`. The probe supplies a nextLink and max_pages=1: the next page is
omitted but the result is reported complete. --all over a large collection can
therefore silently lose data at the default 50-page cap.

Fix: propagate a page-cap signal from the paginator, distinguishing natural
exhaustion from a still-present nextLink. Test top=None, limits larger than the
cap's output, exact natural exhaustion, and the CLI's emitted truncation signal.

### R12 — P2: Org-chart fails at the top of a valid management chain

`src/owa_people/cli.py:390-401`.
The handler still assumes missing manager returns None, although the HTTP
migration now raises NotFoundError. A valid employee without a manager, or a
walk that reaches the top, aborts instead of returning the chart. The probe
returns a valid person followed by a manager 404 and observes the exception.

Fix: catch NotFoundError only around the manager lookup and end the walk;
propagate auth/network errors. Test top-level employees and chains ending before
--depth, and retain direct-report output.

## Plan triage

- Moved all 12 pre-existing checked TODO entries to [DONE.md](../../DONE.md),
  preserving their wording and dates. Added explicit corrections for overbroad
  Drive/cleanup completion claims.
- Retired the obsolete built-in TUI fragments into
  [a historical snapshot](../../done/legacy-todo-2026-09-08.md). `bbfc1c0` removed
  built-in TUIs, followed by `c73ce32` cleanup. This is retirement from the
  CLI-only repository, not a claim the missing TUI plans were finished elsewhere.
- Places remains PARTIAL: package/registration/mock tests exist, but its guessed
  NumberOfLocations DTO conflicts with historical failed-probe notes. No current
  successful live contract was established. Updated its remaining acceptance.
- PIM remains DEFERRED: no package here; historical sibling auth dependency was
  not freshly verified. Removed any implication of current broker certainty by
  adding a dated status banner.
- SWODP readiness remains OPEN: Recall code exists, but the requested live
  Submit→Recall cycle and natural-expiry evidence are still absent. Kept both
  event-driven TODOs; no manufactured production records.
- Reviewed the 14 existing archived plans for status and outstanding intent.
  Added archive banners and an inventory; old checkboxes remain historical
  evidence, not an instruction to resurrect retired work. See
  [archive inventory](archive-triage.md).
- None of the three pre-existing active plans meets all its completion criteria,
  so none was falsely moved to done. New review tasks are tracked in TODO.

## Verification

- Full runtime suite: passed; combined line/branch coverage **92.80%**, above 90%.
- Dedicated owa_core run: **2,560 passed, 5 skipped**; core coverage **97%**,
  above the 95% gate. Raw run output retained in this directory.
- Ruff, compileall, stdlib-only, no-secret and docs-sync checks: passed.
- **12/12 offline defect probes** reproduced the findings above. Only synthetic
  data, mocked boundaries and in-memory outputs are used by those probes.
- Existing coverage tests exercise many helpers but miss combinations such as
  workingHours + JSON rendering, transport errors + overwrite safeguards,
  aliases + shared mode guards, and page caps + truncation metadata.

Run the probes from the repository root:

```sh
.venv/bin/python .plans/reviews/2026-09-08/reproduce.py
```

## Coverage of the review and remaining uncertainty

Reviewed shared auth/config/HTTP/upload/errors/redaction/modes/profile routing,
then targeted dispatch, read/write and normalization paths across all fifteen
consumer packages plus the umbrella. Examined architecture/contract/security
and relevant domain tests, packaging configuration and CI/release workflows.
This is a broad source review with focused executable probes, not exhaustive
path verification or a certification that other defects do not exist.

Additional follow-ups identified statically, not included in the 12 reproduced
findings:

- Scheduling drops workingHours.timeZone and assumes its wall clock matches the
  requested zone. Validate cross-zone/day-boundary behavior against the actual
  response contract before calling local suggestions trustworthy across zones.
- Places silently normalizes unknown payload containers to []; capture-backed
  compatibility checks are needed before calling empty output authoritative.
- PyInstaller spec collects submodules and distribution metadata but does not
  explicitly collect owa_graph/data assets. Build a frozen artifact and exercise
  scope/path discovery before asserting standalone parity.
- Documentation still describes older coverage targets/tool counts and adapters
  retain obsolete “return None” docstrings/dead guards. The docs-sync gate checks
  surface consistency, not semantic truth; it does not catch this drift.

No fresh packaging build, frozen-binary execution, remote-state verification,
live Microsoft behavior, or sibling broker feasibility probe was performed.
Runtime fixes require a subsequent implementation pass; no fixes were silently
mixed into this review.
