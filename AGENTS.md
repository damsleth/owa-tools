# AGENTS.md

Start here for any contributor or coding agent working in `owa-tools`, then
read the nearest local `AGENTS.md` for the files you are editing.

## Suite Purpose

`owa-tools` is one suite distribution with eleven console scripts:
`owa`, `owa-cal`, `owa-mail`, `owa-graph`, `owa-doctor`, `owa-people`,
`owa-sched`, `owa-drive`, `owa-todo`, `owa-planner`, and `owa-sites`.
`owa-piggy` is a separate auth broker repository.

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
- No MCP server, now or later. This is a deliberate, permanent non-goal, not a
  deferred feature. The suite is CLI-only; agents drive it through the
  documented contract - JSON on stdout, the `--agent` envelope, per-tool
  `schema`, and the exit-code taxonomy below. Do not add a Model Context
  Protocol server or propose one.

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

The shared `--doctor` surface emitted by `owa_core.conventions.emit_doctor()`
is a second carve-out. It uses the hugr 0-5 taxonomy that yaams/conventions.py
and ledger/conventions.py also mirror, distinct from the main taxonomy above:

- `0` ok (no findings, or only `info`/`warning`)
- `1` user error (one or more `error` findings)
- `2` transient failure
- `3` auth failure
- `4` not found
- `5` partial success

Anything not invoked through `--doctor` should raise an `owa_core.errors`
subclass instead of returning a `conventions.EXIT_*` constant - this keeps
the main `0/2/10-15/20` contract intact for normal command paths.

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
| `src/owa_core/AGENTS.md` | changing shared auth, HTTP, error, config, version, or secret contracts |
| `src/owa/AGENTS.md` | changing the umbrella discovery binary |
| `src/owa_cal/AGENTS.md` | changing calendar or webcal behavior |
| `src/owa_mail/AGENTS.md` | changing mail behavior |
| `src/owa_graph/AGENTS.md` | changing raw Graph requests, shortcuts, schema hints, or token-emitting helpers |
| `src/owa_doctor/AGENTS.md` | changing health checks |
| `src/owa_people/AGENTS.md` | changing people, contacts, or directory behavior |
| `src/owa_sched/AGENTS.md` | changing scheduling or availability behavior |
| `src/owa_drive/AGENTS.md` | changing OneDrive behavior or binary transfers |
| `src/owa_todo/AGENTS.md` | changing Microsoft To Do task behavior |
| `src/owa_planner/AGENTS.md` | changing Microsoft Planner behavior |
| `src/owa_sites/AGENTS.md` | changing SharePoint behavior |
| `src/tests/AGENTS.md` | adding or changing tests |
| `src/tests/contract/AGENTS.md` | changing machine contract tests |
| `src/tests/compat/AGENTS.md` | changing release-contract compatibility snapshots |
| `src/tests/security/AGENTS.md` | changing secret or security tests |
| `docs/AGENTS.md` | changing user documentation |
| `src/scripts/AGENTS.md` | changing maintenance scripts |

## Reference Docs

The `docs/` tree is mostly user-facing, but a few files are the long-form
rationale behind the terse rules above. Read the relevant one *before* the
matching kind of change - they are reference for agents, not just humans.

| Doc | Read Before |
|---|---|
| `docs/architecture.md` | adding shared abstractions to `owa_core`, or any cross-cutting refactor. Lists the cross-package constraints enforced by `src/tests/test_architecture_contracts.py` (no `urlopen` outside `owa_core.http`, no `owa-piggy` subprocess outside `owa_core.auth`, every mutating command declares confirmation/idempotency, etc.) |
| `docs/testing.md` | adding or restructuring tests - the test layers, fixtures, and coverage gates |
| `docs/new-tool-onboarding.md` | adding a new console script / tool package |
| `docs/security.md` | touching auth, tokens, redaction, config writes, or destructive commands - includes the threat model |
| `docs/agent-integration.md` | changing `--agent`, `--err-json`, schema, or the exit-code surface |
| `docs/profile-model.md` | changing profile / audience precedence |

## Verification

Run the narrow test for your edit first, then run the standard suite before a
commit:

```bash
.venv/bin/ruff check .
.venv/bin/python -m compileall -q src
.venv/bin/python src/scripts/check_stdlib_only.py
.venv/bin/python src/scripts/check_no_secrets.py
.venv/bin/python src/scripts/check_docs_sync.py
.venv/bin/python src/scripts/check_artifacts.py dist/*   # after build
.venv/bin/coverage run --source=owa_core -m pytest -q
.venv/bin/coverage report --fail-under=95
.venv/bin/python -m pytest -q --cov --cov-fail-under=90
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

## Cutting a release (only when the user asks)

The whole suite ships from one distribution (`owa-tools`) on PyPI and from one
Homebrew formula in the `damsleth/homebrew-tap`. `owa-piggy` is released
separately from its own repo. PyPI uploads happen **locally** with `uv publish`
reading `UV_PUBLISH_TOKEN` from `./.env`. The GitHub Actions release workflow
runs gates, builds artifacts, and creates the GitHub Release with the wheel
and sdist attached - it does **not** publish to PyPI.

When the user says "cut a release" / "new patch version" / "ship it":

1. Pick the bump. Patch (`0.1.0 -> 0.1.1`) for bug fixes, doc corrections,
   small UX polish. Minor (`0.1.1 -> 0.2.0`) for new flags, new behaviors,
   anything a user might notice. Never bump major without explicit
   instruction - the suite is 0.x by design.
2. Commit feature work separately from the version bump. Keep one
   `release: vX.Y.Z` commit on top of the feature commits so `git log`
   reads cleanly.
3. Update `pyproject.toml` `version = "X.Y.Z"`. No other file tracks the
   version today.
4. Update `CHANGELOG.md` for the new version.
5. Run all gates locally (these are also the gates the release workflow
   re-runs):
   ```bash
   .venv/bin/ruff check .
   .venv/bin/python src/scripts/check_stdlib_only.py
   .venv/bin/python src/scripts/check_no_secrets.py
   .venv/bin/python src/scripts/check_docs_sync.py
   .venv/bin/coverage run --source=owa_core -m pytest -q
   .venv/bin/coverage report --fail-under=95
   .venv/bin/python -m pytest -q --cov --cov-fail-under=90
   ```
6. Push `main`, then create an **annotated** tag whose message is the
   release notes (short prose summary + bullet list of user-visible
   changes since the previous tag):
   ```
   git tag -a vX.Y.Z -m "vX.Y.Z - <one-line headline>

   <optional prose paragraph>

   - bullet: user-visible change
   - bullet: breaking change (call out explicitly)
   - bullet: internal refactor worth noting
   "
   git push origin vX.Y.Z
   ```
   Never retag a public version - PyPI rejects re-uploads and Homebrew
   users cache the tarball by sha. Lightweight tags (`git tag vX.Y.Z`)
   should not be used.
7. Build sdist + wheel and verify metadata:
   ```bash
   rm -rf dist build
   .venv/bin/python -m build
   .venv/bin/python -m twine check dist/*
   .venv/bin/python src/scripts/check_artifacts.py dist/*
   .venv/bin/python src/scripts/check_console_smoke.py
   ```
8. Publish to PyPI with `uv publish`, which reads `UV_PUBLISH_TOKEN`
   from `./.env` (gitignored - never commit it):
   ```
   set -a && . ./.env && set +a && uv publish dist/owa_tools-X.Y.Z*
   ```
   PyPI's JSON index (`/pypi/owa-tools/json`) lags by minutes after
   upload. If `uv publish` reports "File already exists" on a retry but
   `pypi.org/pypi/owa-tools/X.Y.Z/json` returns 200, the upload
   succeeded and the index is just stale. Don't re-tag or re-build to
   "fix" it.
9. Wait for the tag-triggered release workflow to finish. It re-runs the
   same gates, rebuilds the artifacts in CI, and creates the GitHub
   Release at the tag with the wheel and sdist attached. The workflow
   does not touch PyPI.
10. Bump the Homebrew tap. Fetch the GitHub-generated tarball, compute
    its sha256, and update the formula:
    ```
    curl -sL https://github.com/damsleth/owa-tools/archive/refs/tags/vX.Y.Z.tar.gz \
      -o /tmp/owa-tools-X.Y.Z.tar.gz
    shasum -a 256 /tmp/owa-tools-X.Y.Z.tar.gz
    ```
    Edit `~/Code/homebrew-tap/Formula/owa-tools.rb` - bump the `url`
    tag, the `sha256`, and `version`. Use
    `src/packaging/homebrew/owa-tools.rb` from this repo as the source of
    truth for formula structure. Commit the tap with message
    `owa-tools X.Y.Z` (matches existing tap convention) and push.
11. `brew upgrade owa-tools` on the dev machine to actually pull the
    new formula locally - the tap push only updates metadata; nothing
    on disk changes until brew refetches.

If any step fails midway (tag push rejected, sha mismatch, tap push
rejected, PyPI 4xx that isn't "File already exists"), stop and surface
the error. Do not force-push tags. Do not bump the patch version a
second time to work around an already-published file. A bad release is
fixed by publishing a higher version, not by rewriting history.

`RELEASING.md` is the long-form companion to this section: pre-release
checklist, deferred-work list, and detailed rollback steps.
