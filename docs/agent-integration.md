# Agent integration

This guide covers using the `owa-tools` suite from agents, scripts, and other non-interactive contexts. The contract here is what every consumer tool guarantees once it has been migrated to `owa_core.dispatch` (Phase 3+).

## Contract summary

1. **JSON on stdout by default.** No human prose, no progress text, no warnings.
2. **Logs and errors on stderr.** Always.
3. **Stable exit-code taxonomy.** See [Exit codes](#exit-codes).
4. **Schema export.** Every tool implements `<tool> schema [command]` and `<tool> --help --json`.
5. **Agent envelope (opt-in).** Pass `--agent` or set `OWA_AGENT=1` to wrap output as `{"_owa": {...}, "data": ...}`.
6. **Structured errors (opt-in).** Pass `--err-json` or set `OWA_ERR_JSON=1` to render errors as JSON envelopes on stderr.
7. **No prompts off-TTY.** Destructive commands without `--yes`/`--confirm` exit `2` when stdin is not a TTY.

## Default vs agent mode

The default JSON shape on stdout is unchanged from each tool's pre-migration shape. List commands emit arrays; show commands emit objects. This preserves all existing scripts and pipelines.

Agent mode adds a wrapping envelope:

```json
{
  "_owa": {"tool": "owa-cal", "version": "0.6.3", "schema": 1, "command": "events"},
  "data": [ ... ]
}
```

The `schema` integer is the agent contract version for that command. It bumps only on field removals, renames, type changes, or default-shape changes. Additive fields keep the same number.

Use agent mode when you need self-describing output that survives schema bumps.

## Exit codes

| Code | Meaning                              |
| ---- | ------------------------------------ |
| 0    | success                              |
| 2    | usage error (bad flags, missing arg) |
| 10   | network error                        |
| 11   | auth expired / token refresh needed  |
| 12   | auth scope insufficient              |
| 13   | not found                            |
| 14   | rate-limited after retries           |
| 15   | conflict / precondition failure      |
| 20   | internal error                       |

`owa-doctor probe` overrides this taxonomy with Nagios-style `0/1/2` for back-compat with monitoring tools. Every other consumer follows the suite taxonomy.

## Structured errors

```bash
$ owa-cal events --err-json
{"error": {"code": "AUTH_EXPIRED", "message": "access token rejected (401)", "hint": "re-seed with `owa-piggy setup`", "tool": "owa-cal", "command": "events", "exit_code": 11}}
```

Fields:

- `code`: stable string identifier matching the exception class (e.g., `AUTH_EXPIRED`, `SCOPE_INSUFFICIENT`, `NOT_FOUND`).
- `message`: human-readable one-liner, suitable for log output.
- `hint`: optional remediation hint (may be `null`).
- `tool`, `command`: which tool emitted the error.
- `exit_code`: integer matching the process exit code.

`OWA_ERR_JSON=1` enables this mode globally for an agent's environment.

## Schema export

```bash
$ owa-cal schema events | jq .
{
  "name": "events",
  "summary": "list calendar events",
  "args": [...],
  "flags": [...],
  "destructive": false,
  "schema_version": 1,
  "output_schema": {...},
  "examples": [...]
}
```

Without an argument, `<tool> schema` returns the full Spec (every command). The umbrella `owa schema` aggregates schemas across every installed consumer:

```bash
$ owa schema --tool owa-cal | jq '.[0].schema.commands | map(.name)'
[ "events", "create", "update", "delete", "categories", "config", "refresh", "profiles" ]
```

## Non-TTY behavior

Destructive commands (e.g., `owa-cal delete`, `owa-mail delete`, `owa-drive rm`) refuse to prompt off-TTY. Pass `--yes` or `--confirm` for unattended use:

```bash
# Interactive: prompts y/N
$ owa-mail delete <id>

# Unattended (cron, agent, CI):
$ owa-mail delete <id> --yes
```

Without `--yes` and no TTY, the tool exits `2` with a hint pointing at the flag.

## Pagination

Tools that walk Microsoft's `@odata.nextLink` chains (notably `owa-graph` and `owa-mail`) accept `--all` to follow the chain. In agent mode, list commands surface truncation explicitly:

```json
{
  "_owa": {"tool": "owa-graph", "schema": 1, "pagination": {"truncated": true, "next_link": "..."}},
  "data": [...]
}
```

## Profiles

Every tool delegates auth to `owa-piggy`. Profile selection via `--profile <alias>` matches the alias seeded in `owa-piggy setup`:

```bash
$ owa-piggy --profile work setup
$ owa-cal --profile work events
```

For agent contexts, set `OWA_PIGGY_PROFILE=<alias>` instead of repeating the flag.

## Idempotency

Create/send/upload commands document retry safety. Where a backing API supports an idempotency key, the flag is `--idempotency-key <opaque-string>`. Where it doesn't, the tool documents the retry semantics in `<tool> schema <command>.examples`.

## Cron / scripted use

Minimal pattern:

```bash
#!/usr/bin/env bash
set -euo pipefail
export OWA_AGENT=1
export OWA_ERR_JSON=1
export OWA_PIGGY_PROFILE=cron

# Returns 11 if owa-piggy needs re-seeding; bail before doing real work.
if ! owa-piggy whoami --json >/dev/null; then
  exit 11
fi

owa-cal events --start "$(date -Iseconds)" --end "$(date -d tomorrow -Iseconds)" \
  | jq '.data[] | {start, subject}'
```

## MCP wrappers

The schema contract is designed so that an MCP server can be a thin adapter:

1. List consumers via `owa list --json`.
2. For each, call `<tool> schema` to discover commands/flags.
3. Expose each command as an MCP tool, mapping required args/flags.
4. Run with `OWA_AGENT=1` and `OWA_ERR_JSON=1` so every response is self-describing.

A reference MCP wrapper is out of scope for the consolidation baseline; it can be built once Phase 6 ships.
