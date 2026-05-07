# Changelog

Per-tool changelog for the consumer CLIs. `owa-core` has its own file at `CHANGELOG-core.md`.

Each tool ships from this monorepo as of the migration. Per-tool versions advance independently; the monorepo itself has no separate version.

## owa-cal

### Unreleased

- Now ships from the `owa-tools` monorepo. No CLI change.
- Internal: `owa_cal.jwt` is a thin re-export of `owa_core.jwt`. Public functions (`decode_jwt_segment`, `token_minutes_remaining`) are unchanged.

## owa-mail

### Unreleased

- Now ships from the `owa-tools` monorepo. No CLI change.
- Internal: `owa_mail.jwt` re-exports `owa_core.jwt`.

## owa-graph

### Unreleased

- Now ships from the `owa-tools` monorepo. No CLI change.
- Internal: `owa_graph.jwt` re-exports `owa_core.jwt`. `scopes_in_token` and `scope_in_token` keep their existing shape.

## owa-doctor

### Unreleased

- Now ships from the `owa-tools` monorepo. No CLI change.
- Probe still uses Nagios-style `0/1/2` exit codes; the suite-wide taxonomy applies to every other consumer.

## owa-people

### Unreleased

- Now ships from the `owa-tools` monorepo. No CLI change.

## owa-sched

### Unreleased

- Now ships from the `owa-tools` monorepo. No CLI change.

## owa-drive

### Unreleased

- Now ships from the `owa-tools` monorepo. No CLI change.

## owa (umbrella)

### Unreleased

- New thin discovery binary. Subcommands:
  - `owa list` - JSON list of installed consumers and their versions.
  - `owa schema [--tool <name>]` - aggregate `<tool> schema` output.
  - `owa doctor [...]` - forwards to `owa-doctor probe`.
  - `owa version` - umbrella version.
- Real work still lives in the per-tool binaries.
