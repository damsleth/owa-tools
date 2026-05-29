# New Tool Onboarding

The process that landed `owa-todo` as the ninth consumer binary. Use it as the
template for any tenth tool. Adding a companion CLI should be routine and
low-entropy: a new tool inherits the same auth, config, schema, test, docs, and
agent contracts without copy-pasting a whole existing package.

Paths below are `src/`-relative (the actual layout).

## When to add a new tool

Add a new tool when:

- it targets a distinct Microsoft resource domain,
- it has a user-facing command surface worth naming,
- it can share `owa-piggy` auth and `owa_core` contracts,
- its first version can be tested without live Microsoft access.

Do not add a tool for one-off Graph paths that belong in `owa-graph`.

## Package skeleton

For tool name `owa-foo`:

```text
src/owa_foo/
  AGENTS.md
  __init__.py
  __main__.py
  cli.py
  api.py              # optional thin domain wrapper over owa_core.http
  config.py           # only if the tool has persistent non-secret prefs
  format.py           # only if --pretty has domain-specific output
  models.py           # optional normalizers/builders
docs/
  foo.md
src/tests/foo/
  __init__.py
  conftest.py         # fakes the broker/token boundary (see owa_todo)
  test_cli.py
  test_format.py
  test_models.py
  test_contract.py
```

Required registrations:

- package list in `pyproject.toml`
- console script in `pyproject.toml`
- `owa/cli.py` consumer registry
- root README tool table
- `docs/foo.md`
- `CHANGELOG.md` unreleased section
- root `AGENTS.md` index
- local `owa_foo/AGENTS.md`
- coverage `source` list in `pyproject.toml`
- `check_docs_sync.py` `DOCS` map entry

## Command spec

Every command starts as a `CommandSpec` with: name, summary, auth audience,
flags, positional args, output shape, examples, destructive flag,
streaming/binary stdout flag, and a retry-safety note.

Rules:

- If the command writes, sends, deletes, moves, or marks remote state, declare
  `destructive=True` or `mutating=True`.
- Mutating commands must require explicit confirmation in non-TTY contexts
  unless the command is naturally expected to mutate (such as `send`); even
  then docs must state retry behavior.
- Commands must not parse global flags manually.

## Auth

New tools use `owa_core.auth.get_token`.

Rules:

- no direct subprocess calls to `owa-piggy`
- no imports from `owa_piggy`
- no refresh-token handling
- profile alias only passes through to `get_token`
- audience must be declared in the command spec

## HTTP

Use `owa_core.http.request`.

Rules:

- domain `api.py` may build URLs and call shared HTTP
- no duplicated HTTP error mapping
- no command prints HTTP errors directly
- pagination uses the shared helper

## Config

Only add config when needed, via `owa_core.config.Config` with an allowlist.

Allowed: default profile alias for this tool, default timezone, default page
size, output preferences.

Forbidden: refresh token, access token, tenant secret, password, client secret.

## Output

- Default: JSON on stdout, no stderr on success.
- Pretty: explicit `--pretty`; human text can go to stdout.
- Agent: `--agent` wraps JSON-compatible outputs; binary outputs reject agent
  mode unless written to `--out`.
- Errors: human stderr by default; JSON stderr with `--err-json`.

## Tests required for a new tool

Minimum test set: import smoke; `--help`; `--help --json`; `--version`;
`schema`; unknown command exits `2`; unknown flag exits `2`; missing required
flag exits `2`; auth-broker fake happy path; auth-broker fake failure path; one
success command emits JSON on stdout with empty stderr; one pretty command
emits human output; all path/query/payload builders; all normalizers;
destructive non-TTY behavior if applicable; the no-secret scanner includes the
package; the stdlib-only checker includes the package.

Coverage gate: `owa_foo` must meet the same runtime-package threshold before
merging. See [`testing.md`](testing.md).

## Docs required for a new tool

`docs/foo.md`: purpose; install assumption (`owa-tools` + `owa-piggy`); auth
audience and scope caveats; commands; examples; output shapes; error modes;
retry/idempotency notes; security notes.

README: a short one-line entry only, linking to the doc.

AGENTS (`owa_foo/AGENTS.md`): local invariants; command spec location; nearest
tests; security caveats; the verification command for that package.

## Review checklist

- Does this belong in `owa-graph` instead?
- Does it use only `owa_core` for auth / http / errors?
- Does it introduce runtime dependencies? If yes, reject.
- Are command schemas generated?
- Are output shapes tested?
- Are destructive operations guarded?
- Are examples fake and safe?
- Does the package have a local `AGENTS.md`?
- Does the root index reference it?

## Acceptance checklist

A new tool is onboarded only when:

- a fresh wheel install exposes the binary,
- root `owa list` shows it,
- root `owa schema` includes it,
- tests pass with no live Microsoft access,
- docs and local agent instructions exist.
