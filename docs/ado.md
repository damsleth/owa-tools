# owa-ado

Azure DevOps CLI for Outlook / Microsoft 365 identities.

A thin, pipe-friendly wrapper over the Azure DevOps REST API. JSON on
stdout, logs on stderr, `--pretty` for a human-readable table. Sibling of
`owa-cal` / `owa-mail` / `owa-drive`.

Authentication flows through the `owa-piggy` broker with the `devops`
audience. The profile must have been seeded against the Azure DevOps
client (owa-piggy's non-FOCI capture path) — the FOCI Outlook client
cannot mint a DevOps token (AADSTS65002 preauth wall). Once a profile
brokers `--audience devops`, owa-ado never touches refresh tokens itself.

```
$ owa-ado config --org Norconsult-Group --project NOCOS
default org saved: Norconsult-Group
default project saved: NOCOS

$ owa-ado projects --pretty
name   state       visibility  id
NOCOS  wellFormed  private     928251e9-...
IAM    wellFormed  private     18348743-...

$ owa-ado wi --mine --pretty
id     type        state   assignedTo            title
16972  User Story  New     Carl Joakim Damsleth  Consolidate toolchain
17054  Task        Active  Carl Joakim Damsleth  Add Metier group
```

## Setup

```bash
# Pin the default organisation and project so commands need no flags.
owa-ado config --org <org> --project <project>

# Or pass them via the environment (flags --org/-o and --project/-P also work):
OWA_ADO_ORG=<org> OWA_ADO_PROJECT=<project> owa-ado projects
OWA_ADO_ORG=<org> OWA_ADO_PROJECT=<project> owa-ado wi --mine
```

Resolution order (most specific wins):

- **org**: `--org/-o` › `OWA_ADO_ORG` › config `ado_org`
- **project**: `--project/-P` › `OWA_ADO_PROJECT` › config `ado_project`

`projects` needs only an org; every other command is project-scoped.

## Commands

### `owa-ado projects`

List the projects in the organisation. `--all` follows continuation
tokens; `--pretty` renders a table.

```bash
owa-ado projects --pretty
owa-ado projects --all
```

### `owa-ado sprints`

List a team's iterations (alias: `iterations`). Defaults to the
`<project> Team`; override with `--team`. `--current` returns only the
active iteration.

```bash
owa-ado sprints --current --pretty
owa-ado sprints --team "NOCOS Team"
```

### `owa-ado wi`

Without an id, list work items via WIQL (alias: `workitems`). With a
positional id, show that one work item.

- `--mine` — assigned to me (the default when no other filter or
  `--query` is given)
- `--state <state>` — filter by state (e.g. `Active`, `New`)
- `--type <type>` — filter by work-item type (e.g. `Task`, `Bug`)
- `--top <n>` — cap results (default 50)
- `--query <wiql>` — raw WIQL, overriding the builder

```bash
owa-ado wi --mine --pretty
owa-ado wi --state Active --type Bug --top 20
owa-ado wi 16972 --pretty
owa-ado wi --query "SELECT [System.Id] FROM workitems WHERE [System.State] = 'Active'"
```

### `owa-ado wi-create`

Create a work item. `--type` and `--title` are required. `--assign`
accepts `@me` or an email. `--field path=value` sets any field (bare
names are namespaced under `System.`). `--parent <id>` links a parent.
Confirms before writing unless `--confirm` is passed.

```bash
owa-ado wi-create --type Task --title "Wire reseed" --assign @me --confirm
owa-ado wi-create --type Bug --title "Crash on reload" --field Priority=1 --confirm
```

### `owa-ado wi-update`

Update a work item by id. Set `--state`, `--title`, or any
`--field path=value`. Needs at least one change. Confirms unless
`--confirm` is passed.

```bash
owa-ado wi-update 17054 --state Active --confirm
owa-ado wi-update 17054 --field System.Description="Done" --confirm
```

### `owa-ado wi-comment`

Add a comment to a work item's Discussion. Confirms unless `--confirm`.

```bash
owa-ado wi-comment 17054 --text "Deployed to staging" --confirm
```

### `owa-ado wi-link`

Add a link/relation between two work items. `--target <id>` is the other
work item; `--rel <name>` picks the link type (default `related`; also
`parent`, `child`, `predecessor`, `successor`, `duplicate`, or a
fully-qualified rel reference name). Confirms unless `--confirm`.

```bash
owa-ado wi-link 17054 --target 16972 --rel parent --confirm
owa-ado wi-link 17054 --target 17099 --confirm
```

### `owa-ado wi-unlink`

Remove an existing link to a target work item. Looks up the relation by
target id (narrow with `--rel <name>` when several link types point at the
same item). Confirms unless `--confirm`.

```bash
owa-ado wi-unlink 17054 --target 16972 --confirm
```

### `owa-ado wi-delete`

Delete a work item. Soft-deletes to the project recycle bin by default;
`--destroy` removes it permanently. Destructive — confirms unless
`--confirm`.

```bash
owa-ado wi-delete 17054 --confirm
owa-ado wi-delete 17054 --destroy --confirm
```

### `owa-ado repos`

List repositories (alias: `repositories`). `--all` / `--pretty`.

```bash
owa-ado repos --pretty
```

### `owa-ado prs`

List pull requests, or show one by positional id.

- `--repo <name>` — scope to one repository
- `--status active|completed|abandoned|all` — default `active`
- `--top <n>` — cap results (default 50)
- `--all` — follow continuation tokens, paging until `--top` is reached
  (a stderr note signals when the cap truncates the list)

```bash
owa-ado prs --status active --pretty
owa-ado prs --repo NOCOS-Main --status all
owa-ado prs --status completed --all --top 200
owa-ado prs 2971 --pretty
```

### `owa-ado pipelines`

List pipeline definitions. `--all` / `--pretty`.

```bash
owa-ado pipelines --pretty
```

### `owa-ado runs`

List recent pipeline runs (builds). `--pipeline <id>` filters to one
definition; `--top <n>` caps results (default 20). `--all` pages through
all runs up to `--top`.

```bash
owa-ado runs --top 10 --pretty
owa-ado runs --pipeline 8
owa-ado runs --all --top 100
```

### `owa-ado variable-groups`

List library variable groups, or show one by id (aliases: `library`,
`variablegroups`). Each group's `variables` are included in the JSON; secret
values (which the API withholds) render as `***`. `--all` / `--pretty`.

Pass a group id to show a single group; `--pretty` then renders the name and
a variable/value table.

```bash
owa-ado variable-groups --pretty
owa-ado library --all
owa-ado library 15 --pretty
```

### `owa-ado task-groups`

List task groups (alias: `taskgroups`). `--all` / `--pretty`.

```bash
owa-ado task-groups --pretty
```

### `owa-ado deployment-groups`

List deployment groups (alias: `deploymentgroups`). `--all` / `--pretty`.

```bash
owa-ado deployment-groups --pretty
```

### `owa-ado environments`

List pipeline environments. `--all` / `--pretty`.

```bash
owa-ado environments --pretty
```

### `owa-ado releases`

List releases from Release Management (routed to the `vsrm.dev.azure.com`
host). `--all` / `--pretty`.

```bash
owa-ado releases --pretty
```

### `owa-ado refresh`

Force a token refresh through owa-piggy and verify the org is reachable.

```bash
owa-ado refresh
```

### `owa-ado config`

View or update configuration (`--profile`, `--org`, `--project`).
`--unset <key>` removes one stored key (`ado_org`, `ado_project`,
`owa_piggy_profile`); `--clear` removes them all.

```bash
owa-ado config
owa-ado config --org Norconsult-Group --project NOCOS
owa-ado config --unset ado_project
owa-ado config --clear
```

### `--api-version`

The work-item, PR, and pipeline-run commands accept `--api-version <ver>`
to override the default DevOps API version (`7.1`) for one call — useful
when an org pins an older version or to reach a preview endpoint.

```bash
owa-ado prs --api-version 7.0
owa-ado wi-comment 17054 --text "hi" --api-version 7.1-preview.4 --confirm
```

## Output & exit codes

JSON on stdout by default; `--pretty` for tables. Errors go to stderr
and follow the suite exit-code taxonomy (2 usage, 10 network, 11 auth,
12 scope, 13 not-found, 14 rate-limited, 15 conflict, 20 internal).
`--agent` wraps successful JSON in the suite envelope; `--err-json`
emits structured errors. Multi-profile fan-out (`--profile a --profile
b`) runs the command once per profile and merges the results.
