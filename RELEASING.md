# Releasing

Suite semver. Tags drive releases. The whole suite ships from one
distribution: `owa-tools`. `owa-piggy` is released separately.

## Tag format

- `vX.Y.Z`

The release workflow builds the root `owa-tools` package. It contains the
umbrella `owa` binary plus all consumer CLIs.

## Pre-release checklist

1. Run the split coverage gates:
   ```bash
   coverage run --source=owa_core -m pytest -q
   coverage report --fail-under=95
   pytest -q --cov --cov-fail-under=90
   ```
   Both must be green. The first enforces 95%+ on `owa_core`; the second
   enforces 90%+ across the full runtime surface configured in
   `pyproject.toml`.
2. `python src/scripts/check_stdlib_only.py`, `python src/scripts/check_no_secrets.py`,
   and `python src/scripts/check_docs_sync.py` green.
3. `python -m build`, `python -m twine check dist/*`, and
   `python src/scripts/check_artifacts.py dist/*` green.
4. `python src/scripts/check_console_smoke.py` green.
5. Changelog updated for the suite version.

## Compatibility snapshots

Decision recorded here so it does not drift across docs.

- Releases ship with the `src/tests/compat/` and `src/tests/contract/`
  suites only. The richer snapshot system from the original
  implementation plan (`tools/snapshot_cli.py`, versioned fixture format,
  scrubbed sandbox captures replayed against mocked HTTP) is **deferred**.
- Rationale: the compat + contract gates plus the runtime coverage gate
  are sufficient confidence to publish.
- Follow-up: the snapshot system is tracked as a hardening milestone and
  is listed under `## Deferred work` below.

## Release workflow

PyPI uploads happen **locally** with `uv publish`, which reads
`UV_PUBLISH_TOKEN` from `./.env`. `.env` is gitignored - never commit
it. The GitHub Actions workflow at `.github/workflows/release.yml`
runs gates, rebuilds the artifacts in CI, and creates the GitHub
Release at the tag with the wheel and sdist attached. It does **not**
touch PyPI.

The split is deliberate:

- **Local PyPI publish** keeps the publishing credential out of repo
  secrets and matches the `owa-piggy` release flow on the same machine.
- **CI-built GitHub Release** gives an independent, reproducible build
  artifact published alongside the local PyPI upload, so users can
  verify either source.

### Cutting a release

The compact form (full annotated checklist lives in `AGENTS.md` ->
"Cutting a release"):

```bash
git checkout main
git pull --ff-only

# Bump version in pyproject.toml and add a changelog entry.
$EDITOR pyproject.toml CHANGELOG.md
git commit -am "release: vX.Y.Z"
git push

# Annotated tag with release notes in the message.
git tag -a vX.Y.Z -m "vX.Y.Z - <headline>

- bullet: ...
"
git push origin vX.Y.Z

# Build, verify, publish to PyPI.
rm -rf dist build
.venv/bin/python -m build
.venv/bin/python -m twine check dist/*
.venv/bin/python src/scripts/check_artifacts.py dist/*
.venv/bin/python src/scripts/check_console_smoke.py
set -a && . ./.env && set +a && uv publish dist/owa_tools-X.Y.Z*
```

The tag push also triggers `release.yml`, which re-runs the same gates
and posts the GitHub Release with built artifacts attached. Verify
both:

```bash
pip download --no-deps --dest /tmp/owa-tools-verify owa-tools==X.Y.Z
ls /tmp/owa-tools-verify
```

PyPI's JSON index (`/pypi/owa-tools/json`) lags by minutes after upload.
If `uv publish` reports "File already exists" on a retry but
`pypi.org/pypi/owa-tools/X.Y.Z/json` returns 200, the upload succeeded
and the index is just stale.

## Homebrew

- `owa-tools` formula installs all eight consumer binaries plus the
  umbrella `owa` binary.
- `owa-piggy` formula stays standalone in the same tap.
- A draft formula lives at `src/packaging/homebrew/owa-tools.rb`. It is the
  starting point to copy into the Homebrew tap repository at release
  time. Update `url`, `sha256`, and `version` to match the published
  sdist on PyPI.

## Backout / rollback

If a release introduces a regression:

1. Revert the offending PR on `main`.
2. Bump the patch version, update the changelog, tag `vX.Y.(Z+1)`,
   push the tag, then publish to PyPI locally with `uv publish` as in
   the cut-a-release flow above.
3. Yank the affected version from PyPI if still in the brief window
   where that is safe. Yank via the PyPI web UI at
   <https://pypi.org/manage/project/owa-tools/release/X.Y.Z/> - yanking
   hides it from new resolves but does not delete it.
4. If the broken version is also referenced by the Homebrew formula,
   bump the tap to the fix version (see `AGENTS.md` -> "Cutting a
   release" steps 10-11).
5. Document the regression and the fix version in the changelog.

Never force-push tags. Never delete published versions. A bad release is
fixed by publishing a higher version, not by rewriting history.

## Clean install verification

Before announcing a release, verify outside the development checkout:

```bash
python3 -m venv /tmp/owa-tools-clean
/tmp/owa-tools-clean/bin/pip install owa-tools==X.Y.Z
/tmp/owa-tools-clean/bin/owa list
/tmp/owa-tools-clean/bin/owa schema
/tmp/owa-tools-clean/bin/owa doctor --no-tokens
/tmp/owa-tools-clean/bin/owa-cal --help
/tmp/owa-tools-clean/bin/owa-mail --help
/tmp/owa-tools-clean/bin/owa-graph --help
/tmp/owa-tools-clean/bin/owa-doctor --help
/tmp/owa-tools-clean/bin/owa-people --help
/tmp/owa-tools-clean/bin/owa-sched --help
/tmp/owa-tools-clean/bin/owa-drive --help
/tmp/owa-tools-clean/bin/owa-todo --help
```

Where credentials are available, run at least one read-only authenticated
command per profile (e.g., `owa-piggy status --json`,
`owa-graph me whoami`, `owa-cal events --limit 1`).

For Homebrew, the same checks against the freshly tapped formula:

```bash
brew install owa-tools
owa --version
owa-piggy --version          # must keep working independently
owa list
```

`owa-piggy` and `owa-tools` must work together without either package
importing the other's Python modules. If `owa-tools` ever needs to
inspect `owa-piggy`, it goes through the subprocess JSON surface.

## Deferred work

Tracked here so it does not get lost between releases. None of these
block the first preview release.

- **Compatibility snapshots:** `tools/snapshot_cli.py`, versioned fixture
  format, `src/tests/compat/fixtures/`, scrubbed sandbox captures replayed
  against mocked HTTP.
- **Generated shell completions:** generate from schemas once the schema
  format stabilizes.
- **Broader live integration coverage:** opt-in read-only smoke tests
  across doctor, graph, cal, mail, people, sched, drive.
