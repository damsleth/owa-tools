# owa-planner

Microsoft Planner CLI for Microsoft 365. Read your plans, buckets, and tasks
from the terminal, and perform ETag-protected task writes. Pipe-friendly JSON
by default, `--pretty` for humans.

```sh
brew install damsleth/tap/owa-tools
owa-planner plans --pretty
```

`owa-planner` is part of the `owa-tools` suite and shares the `owa-piggy` auth
broker with the other tools. You can also reach it through the umbrella:
`owa planner plans --pretty` is identical to `owa-planner plans --pretty`.

Planner is **not** Microsoft To Do. They are different products with different
APIs and data models — boards/buckets/tasks vs. To Do lists. For personal To Do
tasks use [`owa-todo`](todo.md); for the group/board Planner use this tool.

---

## Auth and scope

owa-planner talks to the **Microsoft Graph `/planner` surface**
(`https://graph.microsoft.com/v1.0/me/planner/plans`, `.../planner/plans/{id}/
tasks`, …) on the `graph` audience.

The interesting part: the shared token carries **no `Tasks.*` scope**, yet
Planner reads work. Planner is authorized by `Group.ReadWrite.All` (which the
token does carry), verified live — `GET /me/planner/plans` returns `200`. So no
extra setup is required beyond the usual `owa-piggy setup`.

```sh
owa-planner --profile work plans --pretty
```

---

## The output contract

**JSON on stdout, logs on stderr.** Every read command emits parseable JSON by
default; `--pretty` is a human override. So the CLI composes with `jq`:

```sh
owa-planner tasks | jq '[.[] | select(.status != "Completed")] | length'
owa-planner plans | jq '.[] | .id'
```

Tasks are normalized to a stable lowercase shape (camelCase Graph fields hidden):

```json
[
  {
    "id": "task-id-redacted",
    "planId": "plan-id-redacted",
    "bucketId": "bucket-id-redacted",
    "title": "Draft Q3 plan",
    "status": "InProgress",
    "percentComplete": 50,
    "priority": 5,
    "priorityLabel": "medium",
    "due": "2026-06-15",
    "start": "",
    "completed": "",
    "created": "2026-06-01",
    "assignedTo": ["user-guid-redacted"],
    "checklistItemCount": 3,
    "activeChecklistItemCount": 1,
    "referenceCount": 0,
    "hasDescription": true
  }
]
```

`status` is derived from `percentComplete` (`0` → NotStarted, `1`–`99` →
InProgress, `100` → Completed). `priorityLabel` maps Planner's 0–10 priority to
`urgent` / `important` / `medium` / `low`. Date fields are surfaced as the local
`YYYY-MM-DD`. List commands cap at a single page; pass `--all` to follow
`@odata.nextLink` until exhausted.

---

## Commands

```sh
owa-planner plans                             # my plans, JSON
owa-planner plans --pretty                    # title + id
owa-planner plans --group <group-id>          # a group's plans instead of mine

owa-planner buckets --plan <plan-id>          # buckets in a plan
owa-planner buckets --plan <plan-id> --pretty

owa-planner tasks                             # my assigned tasks across plans
owa-planner tasks --plan <plan-id> --pretty   # all tasks in a plan
owa-planner tasks --plan <plan-id> --bucket <bucket-id>
owa-planner tasks --plan <plan-id> --status notstarted

owa-planner task <task-id>                    # one task + checklist + description
owa-planner task --id <task-id> --pretty

owa-planner config --plan <plan-id>           # pin a default plan
owa-planner config --profile work             # pin a default profile
owa-planner refresh                           # force token refresh
```

`--status` accepts `notstarted`, `inprogress`, or `completed`. A task id may be
given as `--id <task-id>` or as a bare positional (`owa-planner task <id>` ==
`owa-planner task --id <id>`). `buckets` and `tasks` fall back to the configured
default plan when `--plan` is omitted (`owa-planner config --plan <id>`).

`task` merges the task with its details (description + checklist + references),
which Graph serves from a separate endpoint, so it is fetched only for the
single-task view, not for list output.

Write commands use Planner `@odata.etag` values and send them back as
`If-Match`. Read the task, task details, or plan details first, then pass the
returned `etag`:

```sh
owa-planner create-task --plan <plan-id> --title "Draft agenda"
owa-planner update-task <task-id> --etag '<etag>' --status completed
owa-planner update-task-details <task-id> --etag '<etag>' --description "Notes"
owa-planner update-plan-details --plan <plan-id> --etag '<etag>' --category category1=Backlog
owa-planner delete-task <task-id> --etag '<etag>' --confirm
```

`delete-task` is destructive and requires `--confirm` in non-interactive use.

---

## Machine / agent surface

Every owa binary exposes the same machine surface (see
[agent-integration.md](agent-integration.md) for the full contract):

- `owa-planner schema [<command>]` - JSON command schema (one command if named)
- `owa-planner --help --json` - the same schema via the help flag
- `--agent` - wrap JSON stdout in a stable `{"_owa": ..., "data": ...}` envelope
  (or set `OWA_AGENT=1`)
- `--err-json` - structured JSON errors on stderr (or `OWA_ERR_JSON=1`)
- `--doctor [--json]` - this tool's health / redaction doctor payload

---

## Notes

- Planner PATCH and DELETE require exact `@odata.etag` values in an `If-Match`
  header. ETags rotate on every write, so write commands refresh the affected
  task/detail after successful mutations when Graph returns no body. The write
  is already committed at that point, so a transient failure of the follow-up
  read does not fail the command — it falls back to a minimal record and notes
  the read failure on stderr.
- `--priority` accepts an integer 0-10 (Planner's priority scale); other values
  are rejected locally with a usage error.
- `assignedTo` lists assignee user GUIDs; name resolution (cross-tool with
  owa-people) is deferred to keep list output to one round-trip.
- The Teams "Tasks by Planner and To Do" app and Project for the Web use
  internal APIs (`tasks.teams.microsoft.com`, `project.microsoft.com`) that the
  shared token cannot reach (the resources don't preauthorize the client). The
  documented Graph `/planner` API used here needs no such access.

See [`AGENTS.md`](../src/owa_planner/AGENTS.md) for repo layout and ground rules.
