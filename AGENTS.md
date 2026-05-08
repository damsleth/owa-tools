# AGENTS.md

Start here for any contributor or coding agent working in `owa-tools`, then
read the nearest local `AGENTS.md` for the files you are editing.

## Suite Purpose

`owa-tools` is one unreleased suite distribution with eight console scripts:
`owa`, `owa-cal`, `owa-mail`, `owa-graph`, `owa-doctor`, `owa-people`,
`owa-sched`, and `owa-drive`. `owa-piggy` is a separate auth broker repository.

Because the suite is unreleased, do not add compatibility shims for old internal
interfaces. Prefer direct migrations to the release contract.

## Global Contracts

- Stdlib only at runtime. No `requests`, `msal`, `pydantic`, `rich`, `click`,
  Microsoft SDKs, or other runtime dependencies.
- JSON goes to stdout by default. Diagnostics, prompts, warnings, and errors go
  to stderr. `--pretty` is the human-output opt-in.
- `owa-piggy` owns refresh tokens, setup, reseed, and profile registry.
  `owa-tools` stores only non-secret preferences and keeps access tokens in
  memory.
- Never import `owa_piggy` Python modules or read `~/.config/owa-piggy`
  directly. Use the `owa-piggy` subprocess JSON surface.
- No live Microsoft or real broker calls in default tests. Live tests must be
  explicitly gated by environment variables.
- No telemetry or update checks.

## Exit Codes

- `0` success
- `2` usage error
- `10` network error
- `11` auth expired
- `12` auth scope insufficient
- `13` not found
- `14` rate-limited
- `15` conflict or precondition failure
- `20` internal error

`owa-doctor probe` has documented health-check exit codes and is the main
command-specific exception.

## Shared Contracts

- New or migrated tools use `owa_core.errors` for expected failures.
- New or migrated auth paths use `owa_core.auth.get_token_for_config()`.
- New or migrated HTTP paths use `owa_core.http.request()` and
  `owa_core.http.paginate()`.
- All broker stderr, HTTP bodies, debug payloads, and structured errors must go
  through `owa_core.secrets.redact()` before rendering.

## Repository Map

| Path | Read When |
|---|---|
| `.plans/` | checking local implementation plans, if present |
| `.github/AGENTS.md` | changing CI or release workflows |
| `owa_core/AGENTS.md` | changing shared auth, HTTP, error, config, version, or secret contracts |
| `owa/AGENTS.md` | changing the umbrella discovery binary |
| `owa_cal/AGENTS.md` | changing calendar or webcal behavior |
| `owa_mail/AGENTS.md` | changing mail behavior |
| `owa_graph/AGENTS.md` | changing raw Graph requests, shortcuts, schema hints, or token-emitting helpers |
| `owa_doctor/AGENTS.md` | changing health checks |
| `owa_people/AGENTS.md` | changing people, contacts, or directory behavior |
| `owa_sched/AGENTS.md` | changing scheduling or availability behavior |
| `owa_drive/AGENTS.md` | changing OneDrive behavior or binary transfers |
| `tests/AGENTS.md` | adding or changing tests |
| `tests/contract/AGENTS.md` | changing machine contract tests |
| `tests/compat/AGENTS.md` | changing release-contract compatibility snapshots |
| `tests/security/AGENTS.md` | changing secret or security tests |
| `docs/AGENTS.md` | changing user documentation |
| `tools/AGENTS.md` | changing maintenance scripts |

## Verification

Run the narrow test for your edit first, then run the standard suite before a
commit:

```bash
.venv/bin/ruff check .
.venv/bin/python -m compileall -q owa owa_core owa_cal owa_mail owa_graph owa_doctor owa_people owa_sched owa_drive tests tools
.venv/bin/python tools/check_stdlib_only.py
.venv/bin/python tools/check_no_secrets.py
.venv/bin/python -m pytest -q --cov=owa_core --cov-fail-under=95
```

For release or packaging changes also run:

```bash
.venv/bin/python -m build
.venv/bin/twine check dist/*
```

## Workflow Rules

- Check `.plans/` before non-trivial work. It is intentionally gitignored and
  may contain current operator context.
- Commit `owa-piggy` changes in the sibling repository, in their own commits,
  only when sibling-repo changes are explicitly authorized.
- Keep changes scoped. One domain per commit is preferred.
- Do not commit build artifacts, virtualenvs, caches, local config, or `.plans/`.
