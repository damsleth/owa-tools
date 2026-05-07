# COMPAT.md

Compatibility contract for the `owa-tools` migration. These rules apply until an explicit schema-major release of the affected tool.

## Hard invariants

1. Existing commands keep their names, positional arguments, flag names, and default output shapes.
2. JSON list commands that emit arrays today keep emitting arrays by default.
3. New metadata envelopes (`_owa`, `_truncated`, `_next`) are available only via `--agent` or `OWA_AGENT=1`. Default JSON output is byte-for-byte compatible.
4. Human rendering remains explicit through `--pretty`.
5. Errors stay human-readable on stderr by default. `--err-json` / `OWA_ERR_JSON=1` is required to switch to structured errors.
6. Destructive commands without a TTY require `--confirm` or `--yes`. Today's interactive prompts are preserved when stdin is a TTY.
7. Stderr text on success stays minimal. No new stderr output on the legacy code path.
8. Exit codes for previously documented commands are preserved. `owa-doctor probe` keeps its `0/1/2` Nagios-style semantics regardless of the suite-wide taxonomy.

## How compatibility is enforced

- `tools/snapshot_cli.py` captures the current command surface per tool: `--help` text, subcommand list, flag list, sample JSON output shape, and observed exit codes.
- Snapshots live in `tests/compat/fixtures/<tool>/<command>.json`.
- The snapshot file format is **frozen at the start of Phase 0**. Changes to the snapshotter itself require regenerating fixtures in their own PR.
- Compatibility tests in `tests/compat/` replay each fixture and assert no drift.
- A failing snapshot blocks merge unless the PR includes a changelog entry explaining the deliberate change.

## How fixtures are captured reproducibly

- Capture against a single sandbox profile (one per developer; not committed).
- Scrub PII (email addresses, names, IDs, tokens) using `tools/snapshot_cli.py --scrub`.
- HTTP responses from Microsoft Graph and Outlook REST are recorded and replayed via mocked transports in CI. Live capture is opt-in (`OWA_LIVE_CAPTURE=1`).
- Fixture replay must succeed without network access.

## Allowed compat-breaking changes during migration

Only with an explicit changelog entry, an updated fixture, and reviewer sign-off:

- Bug fixes that alter previously-broken output (must be called out in the changelog).
- Adding new fields to JSON output (additive only).
- Adding new flags (must default to the legacy behavior).
- Adding new subcommands.

Forbidden without a schema-major release:

- Renaming or removing flags, subcommands, or response fields.
- Changing the default shape of an existing response.
- Reusing an exit code for a different meaning.
- Adding stderr text to the legacy success path.

## Schema versioning

Every agent-mode response includes `"_owa": {"schema": N, ...}`. The integer is the schema version of that command's output.

- Additive changes (new optional fields) keep `schema`.
- Renames, removals, type changes, and default-shape changes bump `schema`.
- A bump requires a changelog entry, a fixture update, and a migration note in `docs/agent-integration.md`.
- The first stable release of agent mode locks `schema` at `1` per command.

## When this document changes

Edits to `COMPAT.md` are themselves migration-sensitive. Treat changes here as policy changes; require a changelog entry.
