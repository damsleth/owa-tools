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

## Local Files

Consumer config files are written atomically through `owa_core.config`:

- config directory mode: `0700`
- config file mode: `0600`
- sibling temp file + fsync + rename
- unknown existing lines are preserved unless the caller uses the allowlisted
  `config_set` path

The suite intentionally does not store access tokens, refresh tokens, client
secrets, cookies, tenant dumps, captured Microsoft responses, or live fixtures.

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
.venv/bin/python tools/check_no_secrets.py
.venv/bin/python tools/check_artifacts.py dist/*
```

Use obvious fake values in tests: `fake-access-token`, `fake-refresh-token`,
and `example.invalid` or `example.com` addresses.

## Live Testing

Default tests must not contact Microsoft or a real broker profile. Live tests
must be opt-in and require explicit environment variables such as
`OWA_LIVE_TESTS=1` and `OWA_PROFILE=<alias>`.
