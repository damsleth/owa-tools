# owa-swodp

`owa-swodp` is the agent-facing data layer for SWODP ServiceNow timesheets. It
does not fetch calendar events or perform matching; use `owa-cal` for calendar
data and pass a reviewed row plan to the write command.

Unlike the Microsoft 365 tools, this command does not use `owa-piggy`. It opens
Microsoft Edge against a dedicated profile, waits for the existing SSO session,
captures ServiceNow cookies and `window.g_ck` through local CDP, closes Edge,
then makes plain stdlib HTTP calls. Captured credentials remain in memory and
are never written to config or emitted. Prod and UAT have separate profiles:
`~/.config/owa-swodp/edge-profile/` and `edge-profile-uat/`.

## Session

```bash
owa-swodp setup --instance prod
owa-swodp setup --instance uat
owa-swodp status --json
owa-swodp reseed --instance prod
```

`owa-swodp status` and `owa-swodp reseed` return exit 11 with a setup hint when
the browser session can no longer silently authenticate.

## Reads

```bash
owa-swodp sync --week-start 2026-08-17
owa-swodp sync --week-start 2026-08-17 --cards-only
owa-swodp cards --week-start 2026-08-17 --range-weeks 3
owa-swodp history
owa-swodp allocations --since 2026-05-01
owa-swodp categories
owa-swodp task TABC123
```

`time_card` access is required and failures are fatal. A 403 from
`resource_allocation` is account-specific and degrades to a warning during
`sync`; time-card data still returns. Row-limit truncation is also explicit.

## Writes

Writes accept a JSON array from a file or stdin. Each row has exactly one of
`taskNumber` or `category`, exactly seven numeric Monday-through-Sunday day
values, a non-empty `description`, and optional `remove` and `split` fields.

`description` is required because SWODP treats the time card's Description as
mandatory. A card saved with a blank one is rejected by the timesheet portal
("The mandatory field \"Description\" is not filled in") and blocks submission
of the whole timesheet, so the plan is refused before any request is sent.
`remove` rows do not need one.

```json
[{"taskNumber":"TABC123","days":[7.5,7.5,0,0,0,0,0],"description":"Implementation and review"}]
```

Exercise remote write behavior against UAT first where a UAT instance exists.
No UAT instance is currently available for every account, so a production-only
verification is permitted with explicit operator authorization and these
controls: snapshot the week, write one reviewed row, verify immediately, and
restore the starting state before moving on.

```bash
owa-swodp write --instance uat --week-start 2026-08-24 --file rows.json --confirm
printf '%s' '[{"category":"admin","days":[1,0,0,0,0,0,0],"description":"Admin"}]' \
  | owa-swodp write --instance uat --week-start 2026-08-24 --file - --confirm
```

## Single-card commands

A time sheet is a set of time cards; `submit` and `delete` act on exactly one
card, addressed by its `sys_id` (from `cards`), and both require confirmation.

```bash
owa-swodp submit --sys-id fa6f509b2bfec3102ba6fe9cf291bf0f --confirm
owa-swodp delete fa6f509b2bfec3102ba6fe9cf291bf0f --confirm
```

Both refuse anything that is not `Pending`, exiting 15, and exit 13 when the
card does not exist. `delete` is the same Table API call `write` makes for a
`remove` row, addressed by id instead of by category or task.

`submit` is not a Table API operation. State transitions go through the Service
Portal processor at
`timecardprocessor.do?sysparm_processor=TimeCardPortalService&sysparm_name=updateTimeCardState`,
form-encoded as `new_state=Submitted&timecard_id=<sys_id>`, which answers with a
bare `{"status": ..., "data": {...}}` object rather than a `result` envelope. A
non-success status is reported as a conflict, and the card's state is read back
afterwards; a card that did not actually move is flagged and exits 15.
Submitting is not reversible from this CLI - undoing it needs a recall in the
portal.

Read the week with the bare binary when the output gates a decision. Wrapping a
read in an output-filtering proxy can drop rows and rewrite field values, which
turns a pre-write snapshot into fiction.

Only `Pending` cards are changed; submitted or approved cards are skipped. New
descriptions use three steps because SWODP drops `comments` on insert: POST
without it, PATCH `comments`, then GET and verify. The batch is not retry-safe
as a whole, requires `--confirm` outside a TTY, and is capped at 200 rows.

## Machine contract

Default output is JSON. `--pretty` indents it, `--agent` adds the suite envelope,
and `--err-json` emits structured stderr. `schema` is offline. Expected failures
use the suite exit taxonomy: notably 11 for an expired sidecar, 12 for required
table denial, 13 for an unknown task number, and 15 for locked/skipped write
preconditions.

The 11 path is covered offline for both an auth-status response and an HTML
sign-in redirect. The signal a live expired SWODP session actually returns is
unverified; treat it as a documented residual risk rather than a known
behavior.
