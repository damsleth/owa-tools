# owa-todo

Microsoft To Do task CLI for Outlook / Microsoft 365. List, create, update,
complete and delete tasks from the terminal. Pipe-friendly JSON by default,
`--pretty` for humans.

```sh
brew install damsleth/tap/owa-tools
owa-todo tasks --pretty
```

`owa-todo` is part of the `owa-tools` suite and shares the `owa-piggy` auth
broker with the other tools. You can also reach it through the umbrella:
`owa todo tasks --pretty` is identical to `owa-todo tasks --pretty`.

---

## Auth and scope

owa-todo talks to the **Outlook REST v2.0 Tasks API**
(`https://outlook.office.com/api/v2.0/me/taskfolders` and `.../me/tasks`) on
the `outlook` audience — the same token owa-cal and owa-mail use. On a To
Do-capable profile that token already carries `Tasks.ReadWrite`, so no extra
setup is required beyond the usual `owa-piggy setup`.

Some tenants apply strict Conditional Access policies that withhold the Tasks
scope. On such a profile owa-todo exits `12` (access denied); switch to a
profile whose policy permits it with `--profile <alias>`.

```sh
owa-todo --profile work tasks --pretty
```

---

## The output contract

**JSON on stdout, logs on stderr.** Every read command emits parseable JSON by
default; `--pretty` is a human override. So the CLI composes with `jq`:

```sh
owa-todo tasks | jq '[.[] | select(.status != "Completed")] | length'
owa-todo lists | jq '.[] | select(.default) | .id'
```

Tasks are normalized to a stable lowercase shape:

```json
[
  {
    "id": "AAMk...redacted",
    "subject": "Buy milk",
    "status": "NotStarted",
    "importance": "High",
    "due": "2026-06-01",
    "start": "",
    "completed": "",
    "reminder": "",
    "categories": [],
    "folderId": "AQMk...redacted"
  }
]
```

Date fields are surfaced in your local timezone. Field names are stable
lowercase; the backend is Outlook REST v2 (PascalCase upstream) but owa-todo
hides that detail.

`tasks` and `lists` cap at a single page by default. Pass `--all` to follow
`@odata.nextLink` until exhausted; `--limit` still controls the page size
(`$top`) requested per round-trip.

---

## Commands

```sh
owa-todo lists                                # task folders (To Do lists), JSON
owa-todo lists --pretty                       # marked default with *

owa-todo tasks                                # all tasks across folders
owa-todo tasks --pretty                       # checklist view
owa-todo tasks --folder "Groceries"           # one folder (by name or id)
owa-todo tasks --status notstarted --pretty   # filter by status
owa-todo tasks --search milk                  # filter by subject

owa-todo create --subject "Buy milk" --due tomorrow --importance high
owa-todo create --subject "Email Ada" --folder "Work" --body "re: Q3 plan"

owa-todo update --id <task-id> --due 2026-06-01
owa-todo update --id <task-id> --status inprogress

owa-todo done --id <task-id>                  # mark completed

owa-todo delete --id <task-id>                # prompts unless --confirm

owa-todo config --folder <folder-id>          # pin a default folder
owa-todo config --profile work                # pin a default profile
owa-todo refresh                              # force token refresh
```

`--due` and `--start` accept `YYYY-MM-DD` plus `today` / `tomorrow` /
`yesterday`. `--importance` is `low`, `normal`, or `high`. `--status` accepts
`notstarted`, `inprogress`, `completed`, `waiting`, or `deferred`.

`create`, `update`, and `done` return the single normalized task. `delete` is
guarded: in a non-interactive context it requires `--confirm`, otherwise it
prompts before deleting.

Tasks carry opaque ids: address one via `--id` or as a bare positional argument
(`owa-todo done <id>` == `owa-todo done --id <id>`).

---

## Machine / agent surface

Every owa binary exposes the same machine surface (see
[agent-integration.md](agent-integration.md) for the full contract):

- `owa-todo schema [<command>]` - JSON command schema (one command if named)
- `owa-todo --help --json` - the same schema via the help flag
- `--agent` - wrap JSON stdout in a stable `{"_owa": ..., "data": ...}`
  envelope (or set `OWA_AGENT=1`)
- `--err-json` - structured JSON errors on stderr (or `OWA_ERR_JSON=1`)
- `--doctor [--json]` - this tool's health / redaction doctor payload

---

## Notes

- The live To Do web app uses an internal `substrate.office.com/todob2` API;
  owa-todo targets the documented Outlook REST v2.0 Tasks endpoints instead
  because they work on the existing `outlook` token and mirror owa-cal.
- Task notes (`Body`) are HTML upstream and are omitted from the normalized
  list output to keep it compact.

See [`AGENTS.md`](../src/owa_todo/AGENTS.md) for repo layout and ground rules.
