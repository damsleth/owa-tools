# Architecture and Maintainability

The standing rulebook for keeping entropy out of `owa-tools` as the suite is
maintained. Re-read this before adding shared abstractions to `owa_core` or
landing a new tool.

The goal: keep the suite small, predictable, and maintainable as it grows.
There should be one obvious way to do common work - parse commands, get tokens,
make HTTP calls, render output, emit errors, and test behavior.

## Low-entropy architecture

### One distribution

One suite version, one wheel, one Homebrew formula.

Avoid:

- per-tool package directories with their own build metadata
- per-tool version parsing
- path dependencies between packages inside the same wheel

### One shared contract layer

Use `owa_core` for: auth, HTTP, errors, config, dispatch, schema, TTY
confirmation, redaction, and version.

Avoid:

- duplicated `_error`
- duplicated `_require_value`
- duplicated HTTP status mapping
- direct `sys.exit` in handlers
- command-specific JSON schema handcrafting

### Thin domain packages

Each tool package should contain command declarations, domain URL/path
builders, payload builders, normalizers, and pretty formatters.

It should not contain subprocess auth mechanics, generic HTTP retry logic, a
generic config parser, generic schema generation, or generic error rendering.

## Runtime dependency policy

Runtime: Python stdlib only.

Dev: pytest, pytest-cov, ruff, and uv (used for both `uv build` and `uv publish`).

`src/scripts/check_stdlib_only.py` gates runtime imports in CI. Allowed runtime
imports are the Python stdlib, the `owa_*` packages in this repo, and
`owa-piggy` (subprocess only). Add a package allowlist entry when a new package
is introduced.

## Ruff and formatting

One code style, enforced by `ruff format .` and `ruff check .`.

```toml
[tool.ruff]
line-length = 100
target-version = "py310"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "B", "UP", "SIM", "C4", "RUF"]
ignore = []
```

If rules are too noisy, narrow them deliberately - do not leave CI running a
Ruff config the repo cannot pass. Standing cleanup: no semicolon
multi-statements, sorted imports, no unused imports, no ambiguous variable
names like `l`, no f-strings without placeholders.

## Error-message quality

Human errors should be short, actionable, specific, and carry no traceback by
default:

```text
ERROR: auth expired. Run: owa-piggy reseed --profile work
```

Structured errors (with `--err-json` or `OWA_ERR_JSON=1`) carry a stable shape:

```json
{
  "error": {
    "code": "AUTH_EXPIRED",
    "message": "auth expired",
    "hint": "owa-piggy reseed --profile work",
    "tool": "owa-mail",
    "command": "messages",
    "exit_code": 11
  }
}
```

## Maintainability tests

Architecture-constraint tests keep entropy from creeping back in:

- no `sys.exit` outside `main` modules and `if __name__ == "__main__"`
- no `urllib.request.urlopen` outside `owa_core.http` and tightly documented
  exceptions
- no `subprocess.run(["owa-piggy", ...])` outside `owa_core.auth`
- no direct `print(json.dumps(...))` in handlers (dispatch owns rendering),
  except streaming commands
- every command has a schema
- every mutating command declares confirmation / idempotency metadata

The sole current `urlopen` exception is `owa_swodp.cdp`: target discovery talks
only to the loopback Edge debugging endpoint. Remote SWODP HTTP still routes
through `owa_core.http.request_unauthenticated`.

See `src/tests/test_architecture_contracts.py` and `src/tests/docs/`.

## Documentation set

- `README.md` - suite overview, install, auth model, tool list, quick
  examples, versioning, security boundary.
- `docs/profile-model.md` - profile precedence, `owa-piggy` ownership, per-tool
  defaults.
- `docs/agent-integration.md` - `--agent`, `--err-json`, schemas, exit codes,
  stdout/stderr, examples for scripts.
- `docs/security.md` - the broker boundary, what the suite does not store,
  redaction, and live-test rules.
- `docs/testing.md` - test layers, coverage gates, data policy.
- `docs/new-tool-onboarding.md` - the process for adding a companion CLI.
- per-tool docs: `docs/{cal,mail,graph,doctor,people,sched,drive,todo}.md`.
- `CONTRIBUTING.md` - setup, tests, AGENTS, code style.
- `RELEASING.md` - suite release flow.

### Drift prevention

`src/scripts/check_docs_sync.py` verifies that every command in a tool's schema
appears in its per-tool doc, that docs examples use known commands, that the
README tool list matches the `owa/cli.py` registry, that root `AGENTS.md` index
paths exist, and that no doc advertises a stale per-tool install snippet.
`src/tests/docs/test_docs_sync.py` runs it in the suite.

## Refactor sequence

When migrating shared behavior, move incrementally rather than rewriting every
package at once:

1. Make formatting pass.
2. Add shared errors and version.
3. Add shared auth around current broker calls.
4. Add shared HTTP and migrate one small tool.
5. Add dispatch / schema for one small tool.
6. Migrate remaining tools.
7. Delete obsolete adapters and duplicated helpers.
8. Add architecture tests to prevent regression.

## Review checklist

For every PR:

- Does this reduce or increase duplicated patterns?
- Did new command behavior land with schema and tests?
- Did docs change when command behavior changed?
- Are errors typed?
- Are secrets redacted?
- Is the nearest `AGENTS.md` still accurate?
- Does this need a release note?
