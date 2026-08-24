# Security Model

`owa-tools` is a token consumer. `owa-piggy` is the auth broker and the only
component that stores refresh tokens.

## Boundaries

- `owa-piggy` owns setup, reseed, refresh-token storage, profile registry, and
  token minting.
- `owa-tools` calls `owa-piggy` over its JSON subprocess contract and keeps
  access tokens in memory only for the duration of one command.
- `owa-tools` config files store non-secret preferences: profile aliases,
  default audiences, default timezones, work windows, and debug flags.
- `owa-tools` must not read `~/.config/owa-piggy` directly and must not import
  `owa_piggy` Python modules.

`owa-swodp` is a separate ServiceNow credential domain and does not use the
broker. It owns dedicated prod/UAT Edge userdata directories under
`~/.config/owa-swodp/`. CDP-captured cookies and `g_ck` stay in memory for one
command and are never written by the CLI or emitted.

## Local Files

Consumer config files are written atomically through `owa_core.config`:

- config directory mode: `0700`
- config file mode: `0600`
- sibling temp file + fsync + rename
- unknown existing lines are preserved unless the caller uses the allowlisted
  `config_set` path

The suite intentionally does not store access tokens, refresh tokens, client
secrets, cookies, tenant dumps, captured Microsoft responses, or live fixtures.
The SWODP Edge userdata directories are the one explicit exception: they are
browser profiles and necessarily contain browser-managed ServiceNow session
state. The directories are mode `0700` where supported.

## Output

JSON is stdout. Diagnostics, prompts, warnings, and errors are stderr.

Expected failures use the shared exit-code taxonomy:

- `2` usage error
- `10` network error
- `11` auth expired
- `12` scope insufficient
- `13` not found
- `14` rate-limited
- `15` conflict or precondition failure
- `20` internal error

Structured errors are available with `--err-json` or `OWA_ERR_JSON=1`.

## Redaction

Before rendering broker stderr, HTTP debug bodies, Authorization headers, or
structured errors, route content through `owa_core.secrets.redact()`.

The scanner and artifact checks reject token-shaped content in source, tests,
wheels, and sdists:

```bash
.venv/bin/python src/scripts/check_no_secrets.py
.venv/bin/python src/scripts/check_artifacts.py dist/*
```

Use obvious fake values in tests: `fake-access-token`, `fake-refresh-token`,
and `example.invalid` or `example.com` addresses.

## Threat model

### Token leakage

Risks: debug logs print Authorization headers; structured errors include broker
stderr with token content; fixtures accidentally contain real tokens; `--curl`
or `--az` emit bearer tokens into shell history or clipboard; tests snapshot
access tokens.

Mitigations: a central `owa_core.secrets.redact(value)`; debug paths redact
before printing; the no-token scanner runs in CI; the fixture policy is
documented in `src/tests/security/AGENTS.md`. `owa-graph`'s `--curl` / `--az`
render a `$OWA_TOKEN` placeholder by default and require `--include-token` to
inline the real bearer, so `owa-graph GET /me --curl | pbcopy` never puts a
live token on the clipboard (see [`graph.md`](graph.md)).

### Refresh-token boundary drift

Risks: a future tool reads `owa-piggy` config directly for convenience; setup /
reseed logic migrates into `owa-tools`.

Mitigations: the stdlib import checker bans `owa_piggy` imports in `owa-tools`;
security tests scan for paths like `.config/owa-piggy`, `OWA_REFRESH_TOKEN`, and
`profiles/default/config` outside docs and explicit tests; the root `AGENTS.md`
forbids direct broker storage reads.

### Path traversal

Risks: profile aliases used as paths; OneDrive remote paths escape expected
Graph path encoding; local `--out` writes unintended files.

Mitigations: profile aliases are only passed to `owa-piggy`, never used for
local path construction; path builders are pure functions with traversal tests;
`--out` writes exactly where the user points, with clear parent errors and no
implicit overwrite unless guarded by `--force`.

### Destructive commands

Risks: `delete`, `rm`, `move`, `mark`, `send`, and other write operations run in
scripts by accident.

Mitigations: non-TTY destructive commands require `--confirm` or `--yes`;
high-impact commands document retry safety; the confirmation helper exits `2`,
not a generic failure.

### Overbroad scopes

Risks: a tool silently uses a more privileged audience or scope than needed.

Mitigations: every command spec declares its audience and scope assumptions;
`owa-graph` scope hints stay advisory and redacted; no command changes the
`owa-piggy` default audience; user-provided `--audience` is always explicit.

## Live Testing

Default tests must not contact Microsoft or a real broker profile. Live tests
must be opt-in and require explicit environment variables such as
`OWA_LIVE_TESTS=1` and `OWA_PROFILE=<alias>`.
