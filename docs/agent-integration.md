# Agent Integration

The command surface is designed for scripts and coding agents first: stable
schemas, JSON stdout, structured errors, and predictable exit codes.

## Discoverability

Every consumer binary exposes the same introspection surface:

```bash
owa-mail --help --json
owa-mail schema
owa-mail schema messages
owa schema
owa schema --tool owa-mail
```

The schema includes the suite version, schema version, command names, basic
auth audience metadata, output type, declared flags, and mutation metadata.
Destructive commands declare `destructive: true` and their confirmation flag.

## Success Output

Use `--agent` or `OWA_AGENT=1` when a caller needs a stable envelope around
JSON-compatible command output:

```bash
owa-mail --agent schema messages
```

The envelope shape is:

```json
{
  "_owa": {
    "suite": "owa-tools",
    "tool": "owa-mail",
    "version": "0.1.0",
    "schema_version": 1,
    "command": "schema"
  },
  "data": {}
}
```

Human output such as `--pretty` is intentionally not agent-wrapped. Binary
stdout is also rejected in agent mode unless the command writes bytes to a file,
for example `owa-drive get <path> --out <file>`.

## Error Output

Use `--err-json` or `OWA_ERR_JSON=1` for machine-readable stderr:

```bash
owa-mail --err-json messages
```

Shape:

```json
{
  "error": {
    "code": "AUTH_EXPIRED",
    "message": "owa-piggy not found in $PATH",
    "hint": "Install with: brew install damsleth/tap/owa-piggy",
    "tool": "owa-mail",
    "command": "messages",
    "exit_code": 11
  }
}
```

Messages are redacted before rendering. Do not parse human stderr when
structured mode is available.

## Safe Automation

- Treat exit code `2` as caller error and do not retry unchanged input.
- Treat `10`, `14`, and some `20` failures as retry candidates only when the
  surrounding workflow can safely repeat the command.
- Destructive commands require `--confirm` in non-interactive contexts.
- Live Microsoft calls are never required for schema, help, version, config, or
  packaging smoke checks.

## Repo Maintenance

Agents editing the codebase should start at the root `AGENTS.md`, then read the
nearest local `AGENTS.md`. The root file indexes each local instruction file and
the tests enforce that runtime packages keep local guidance.
