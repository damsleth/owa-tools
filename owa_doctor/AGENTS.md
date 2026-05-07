# AGENTS.md

Instructions for AI coding agents working in this repo.

## What this is

`owa-doctor` is a stdlib-only Python CLI that probes the rest of the
`owa-*` suite and reports which CLIs are installed, what version, and
whether each `owa-piggy` profile can still mint a token. JSON on
stdout, logs on stderr, `--pretty` for humans.

It owns no auth and stores no config. Every fact in its report comes
from running another CLI (`owa-piggy`, sibling `owa-*` tools) and
parsing stdout.

## Ground rules

- **Stdlib only** at runtime. No `requests`, no deps. `pytest` is
  dev-only under `[project.optional-dependencies] test`.
- **JSON on stdout, logs on stderr.** `--pretty` switches stdout to
  a human-readable rendering. Never decorate the JSON path.
- **No process exits inside `probe.py`.** Probes return structured
  findings; the CLI dispatcher is the only place allowed to call
  `sys.exit`. This keeps probes testable and lets a single bad
  profile not abort the whole report.
- **Do not import owa-piggy as a Python module.** Treat it as a
  POSIX util on PATH. Version skew between the two is normal and
  the JSON token contract is the bridge.
- **Never commit real tokens, profile aliases that map to real
  tenants, or actual `~/.config/owa-*/` contents** in tests or
  fixtures. Use obvious fakes.

## Layout

```
owa_doctor/
  __init__.py     # re-exports `main` so `owa-doctor = "owa_doctor:main"` resolves
  __main__.py     # `python -m owa_doctor`
  cli.py          # arg parsing + report assembly + exit-code policy
  probe.py        # health probes (return structured findings, never exit)
  format.py       # --pretty renderer
  jwt.py          # JWT segment decode (exp + aud only, no sig check)
tests/            # pytest suite, no network
pyproject.toml
```

## Working on this repo

- Each new health check is a function in `probe.py` returning a JSON-
  serialisable dict. The CLI composes them.
- Exit-code policy lives in `cli._exit_code_for(report)` and is the
  one place to change it. Don't scatter exit codes into probes.
- Pretty rendering belongs in `format.py`. The JSON shape is the
  contract; the table is the view.

## Verification before claiming done

- `python -m compileall -q owa_doctor` passes.
- `python -m owa_doctor --help` runs without traceback on a clean
  machine (no owa-piggy required for help).
- `python -m owa_doctor --no-tokens` runs and produces a valid
  JSON report with no owa-piggy on PATH.
- `pytest -q` is green.

## What NOT to do

- Don't add a config file or per-profile state. `owa-doctor` is
  stateless by design.
- Don't add network calls. Probes shell out to siblings; the
  siblings own their network. Adding a Graph ping here would
  duplicate auth code that already lives in owa-piggy + siblings.
- Don't parse the human-format `owa-piggy status` output for
  facts you can derive from a JWT. JWT decode is more reliable
  than scraping a free-text field.
