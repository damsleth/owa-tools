# owa-tools

Monorepo for the seven `owa-piggy` consumer CLIs: `owa-cal`, `owa-mail`, `owa-graph`, `owa-doctor`, `owa-people`, `owa-sched`, `owa-drive`. Plus the umbrella `owa` discovery binary.

The auth broker `owa-piggy` lives in its own repository. It is the only persistent-secret holder in the suite.

## Status

`owa-tools` is currently unreleased and uses one suite version for all console scripts.

| CLI | Status |
|---|---|---|
| `owa-cal` | beta |
| `owa-mail` | beta |
| `owa-graph` | beta |
| `owa-doctor` | alpha |
| `owa-people` | alpha |
| `owa-sched` | alpha |
| `owa-drive` | alpha |
| `owa` | umbrella discovery binary |

## Layout

```
owa-tools/
├── owa_cal/         calendar CRUD over Outlook REST
├── owa_mail/        mail CRUD over Outlook REST
├── owa_graph/       Microsoft Graph CLI (verb-first + 14 resource shortcut groups)
├── owa_doctor/      health check across the suite
├── owa_people/      people, directory, contacts (Graph)
├── owa_sched/       free/busy and slot finding (Graph)
├── owa_drive/       OneDrive CRUD (Graph)
├── owa/             umbrella `owa` binary (list, schema, doctor, version)
├── tools/           CI helpers (stdlib check)
├── tests/           per-tool test suites
├── completions/     bash, zsh, fish
└── docs/            per-tool docs
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

The wheel contains all eight console scripts (`owa`, `owa-cal`, `owa-mail`, `owa-graph`, `owa-doctor`, `owa-people`, `owa-sched`, `owa-drive`) and they all report the same `owa-tools` suite version.

Test suite:

```bash
.venv/bin/python -m pytest
.venv/bin/python tools/check_stdlib_only.py
```

See `RELEASING.md` for the suite tag-and-publish flow.

## Conventions

- Stdlib only at runtime, except for the local suite packages and `owa-piggy`.
- JSON on stdout, logs on stderr, `--pretty` for humans.
- Auth via `owa-piggy` (subprocess, JSON contract).
- See `AGENTS.md` for the agent contract.

## License

MIT.
