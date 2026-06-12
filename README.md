# owa-tools

Pipe-friendly CLI suite for Outlook and Microsoft 365. Calendar, mail, Graph,
OneDrive, scheduling, people lookup, health checks - all from your terminal,
all returning JSON by default.

[![PyPI](https://img.shields.io/pypi/v/owa-tools.svg)](https://pypi.org/project/owa-tools/)
[![GitHub release](https://img.shields.io/github/v/release/damsleth/owa-tools.svg)](https://github.com/damsleth/owa-tools/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

No Azure AD app registration. No third-party runtime dependencies. Auth piggybacks
on the OWA browser session via [`owa-piggy`](https://github.com/damsleth/owa-piggy)
- separate package, separate token store, never imported.

Every `owa-*` binary shares one CLI contract - the same output classes, exit
codes, and JSON envelopes - so they behave consistently and compose cleanly in
scripts and pipelines.

## Install

Homebrew (recommended):

```bash
brew install damsleth/tap/owa-piggy damsleth/tap/owa-tools
```

PyPI:

```bash
pipx install owa-piggy && pipx install owa-tools
```

Either path lands fourteen binaries on your PATH (`owa`, `owa-cal`, `owa-mail`,
`owa-graph`, `owa-doctor`, `owa-people`, `owa-sched`, `owa-drive`, `owa-todo`,
`owa-planner`, `owa-sites`, `owa-teams`, `owa-vids`, `owa-ado`) plus the
`owa-piggy` auth broker.

## Quickstart

```bash
# 1. One-time auth setup (opens Edge, signs you in, captures a refresh token)
owa-piggy setup --profile work --email you@yourcompany.com

# 2. Verify everything's healthy
owa doctor

# 3. Try it
owa-cal events --pretty                          # today's calendar
owa-mail folders                                 # mail folders
owa-graph me whoami                              # who am I
owa-drive ls                                     # OneDrive root
owa-people find "ola nordmann"                   # people lookup
owa-sched availability --who you@example.com --date today
```

Every binary supports `--help` and `<binary> help` for the full command surface.
JSON on stdout, logs on stderr, `--pretty` when you want a human-readable table.

The `owa` umbrella also dispatches to any tool, so `owa cal events --pretty`
is equivalent to `owa-cal events --pretty` — everything after the tool name is
passed straight through.

## What's in the box

| CLI | What it does |
|---|---|
| `owa-cal` | Calendar CRUD over Outlook REST. Events, categories, recurrence. |
| `owa-mail` | Mail CRUD: messages, send, reply, forward, folders. |
| `owa-graph` | Microsoft Graph CLI: verb-first plus 14 resource shortcut groups. |
| `owa-people` | People, directory, and contacts via Graph. |
| `owa-sched` | Free/busy and slot finding for one or many attendees. |
| `owa-drive` | OneDrive CRUD plus binary up/download. |
| `owa-doctor` | Health check across the suite, all profiles, all audiences. |
| `owa-todo` | Microsoft To Do tasks: lists, create, update, complete, delete. |
| `owa-planner` | Microsoft Planner (read-only): plans, buckets, tasks, task detail. |
| `owa-sites` | SharePoint (read-only) via SharePoint REST: site, lists, items, files, search. |
| `owa-teams` | Microsoft Teams (read-only): joined teams, channels, chats, and channel/chat messages (threaded). |
| `owa-vids` | Download Teams / OneDrive meeting-recap DASH streams and mux to MP4 (token-only, via ffmpeg). |
| `owa-ado` | Azure DevOps: work items (WIQL), boards/sprints, repos & pull requests, pipelines & runs. Auth via `owa-piggy --audience devops`. |
| `owa` | Umbrella: suite meta (`owa list`, `owa schema`, `owa version`, `owa --doctor`) plus `owa <tool> ...` pass-through dispatch (e.g. `owa cal events`). |

## Multi-account / profiles

Each tool delegates auth to `owa-piggy` and inherits its profile model. Pin a
profile for a tool, switch per call, or set it via env:

```bash
owa-cal --profile crayon events --pretty         # one call
OWA_PROFILE=crayon owa-cal events --pretty       # one shell session
owa-cal config --profile crayon                  # persistent for owa-cal
```

Repeat `--profile` to fan out across profiles in one call - results are merged
keyed by profile (exit `0` all ok, `2` mixed, `1` all failed):

```bash
owa-mail --profile crayon --profile brkh messages --unread   # both inboxes, merged
```

See [`docs/profile-model.md`](docs/profile-model.md) for the full precedence
rules.

## For agents and automation

- JSON on stdout by default. `--pretty` is the human opt-in.
- `--agent` wraps output for automation tooling; `--err-json` emits structured
  stderr.
- `owa schema` aggregates per-tool schemas for discovery.
- Exit code taxonomy is shared across the suite (`docs/agent-integration.md`).

## Docs

- [`docs/security.md`](docs/security.md) - token, redaction, threat model, and live-test boundaries
- [`docs/agent-integration.md`](docs/agent-integration.md) - schema discovery, `--agent`, `--err-json`
- [`docs/profile-model.md`](docs/profile-model.md) - profiles and audiences
- Per-tool: [`cal`](docs/cal.md) | [`mail`](docs/mail.md) | [`graph`](docs/graph.md) | [`doctor`](docs/doctor.md) | [`people`](docs/people.md) | [`sched`](docs/sched.md) | [`drive`](docs/drive.md) | [`todo`](docs/todo.md) | [`planner`](docs/planner.md) | [`sites`](docs/sites.md) | [`teams`](docs/teams.md) | [`vids`](docs/vids.md)

Maintainer reference:

- [`docs/architecture.md`](docs/architecture.md) - low-entropy architecture, shared contracts, maintainability tests
- [`docs/testing.md`](docs/testing.md) - test layers, coverage gates, data policy
- [`docs/new-tool-onboarding.md`](docs/new-tool-onboarding.md) - process for adding a companion CLI

## Releases

- PyPI: <https://pypi.org/project/owa-tools/>
- GitHub Releases: <https://github.com/damsleth/owa-tools/releases>
- Homebrew tap: <https://github.com/damsleth/homebrew-tap>
- Changelog: [`CHANGELOG.md`](CHANGELOG.md)

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for setup, tests, coverage gates,
commit conventions, and code style. The release flow lives in
[`RELEASING.md`](RELEASING.md), and architecture/agent guidance lives in
[`AGENTS.md`](AGENTS.md).

## License

MIT.
