# owa-tools

Monorepo for the seven `owa-piggy` consumer CLIs: `owa-cal`, `owa-mail`, `owa-graph`, `owa-doctor`, `owa-people`, `owa-sched`, `owa-drive`. Plus `owa-core`, the shared library they all sit on.

The auth broker `owa-piggy` lives in its own repository. It is the only persistent-secret holder in the suite.

## Status

Phases 0-7 of the migration are in place. The monorepo builds a single wheel that installs all eight binaries; `owa_core` is in use as a shared library; the agent contract is implemented and tested. Per-tool releases happen from this repo.

| CLI | Current version | Status |
|---|---|---|
| `owa-cal` | 0.6.2 | beta |
| `owa-mail` | 0.1.1 | beta |
| `owa-graph` | 0.2.0 | beta |
| `owa-doctor` | 0.1.0 | alpha |
| `owa-people` | 0.1.0 | alpha |
| `owa-sched` | 0.1.0 | alpha |
| `owa-drive` | 0.1.0 | alpha |
| `owa` | 0.0.0.dev0 | umbrella discovery binary |

## Layout

```
owa-tools/
├── owa_core/        shared library (auth, http, jwt, config, dates, format, dispatch, errors, tty)
├── owa_cal/         calendar CRUD over Outlook REST
├── owa_mail/        mail CRUD over Outlook REST
├── owa_graph/       Microsoft Graph CLI (verb-first + 14 resource shortcut groups)
├── owa_doctor/      health check across the suite
├── owa_people/      people, directory, contacts (Graph)
├── owa_sched/       free/busy and slot finding (Graph)
├── owa_drive/       OneDrive CRUD (Graph)
├── owa/             umbrella `owa` binary (list, schema, doctor, version)
├── tools/           CI helpers (stdlib check, snapshot capture, schema diff)
├── tests/
│   ├── compat/      command-surface snapshots
│   ├── contract/    agent-mode contract assertions
│   └── integration/ opt-in live tests
├── completions/     bash, zsh, fish (generated from schemas)
└── docs/
```

## Running

Local dev install:

```bash
python3 -m venv .venv
.venv/bin/pip install -e .[dev]
.venv/bin/owa list
```

Wheel build:

```bash
.venv/bin/python -m build --wheel
```

The wheel contains all eight console scripts (`owa`, `owa-cal`, `owa-mail`, `owa-graph`, `owa-doctor`, `owa-people`, `owa-sched`, `owa-drive`).

Test suite:

```bash
.venv/bin/python -m pytest          # owa_core unit tests + agent contract tests
.venv/bin/python tools/check_stdlib_only.py
```

See `RELEASING.md` for the per-tool tag-and-publish flow and `docs/migrating-from-individual-installs.md` for the user upgrade path.

## Conventions

- Stdlib only at runtime, except for the local suite packages (`owa-core`, `owa-piggy`).
- JSON on stdout, logs on stderr, `--pretty` for humans.
- Auth via `owa-piggy` (subprocess, JSON contract).
- See `AGENTS.md` for the full agent contract and `COMPAT.md` for the compatibility rules that govern the migration.

## License

MIT.
