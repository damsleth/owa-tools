# owa-doctor

Health check for the owa-* suite.

One command, structured report: which CLIs are installed, which
[`owa-piggy`](https://github.com/damsleth/owa-piggy) profiles can
still mint a token, and which are about to expire.

```text
$ owa-doctor --pretty
owa-piggy: ok (0.11.0) at /opt/homebrew/bin/owa-piggy

Siblings:
  cli         state    version
  owa-cal     ok       0.2.1
  owa-mail    ok       0.2.1
  owa-graph   ok       0.2.1
  owa-doctor  ok       0.2.1
  owa-people  ok       0.2.1
  owa-sched   ok       0.2.1
  owa-drive   ok       0.2.1
  owa-todo    ok       0.2.1

Profiles (audience=graph):
  alias    default  state  mins-left  note
  work              ok     78
  crayon            fail   -          AADSTS70043 refresh token expired
  home              ok     77
  agent    yes      ok     72

Summary: 3 ok, 0 warn, 1 fail
```

## Install

Part of the `owa-tools` suite — one install gives you all nine binaries plus the `owa-piggy` auth broker:

```bash
brew install damsleth/tap/owa-piggy damsleth/tap/owa-tools
# or: pipx install owa-piggy && pipx install owa-tools
```

Run as `owa-doctor ...` or via the umbrella `owa doctor ...`.

## Auth

owa-doctor does not own auth state of its own. The `probe` shells out to
`owa-piggy` to mint a token per profile, and to the sibling CLIs to check
their versions; `owa-piggy` owns the refresh token and profile registry.
Audience: graph by default (pass `--audience outlook` to verify Outlook REST
is reachable too).

```bash
owa-piggy setup --profile work        # one-time, opens a browser
```

See [profile-model.md](profile-model.md) for profile precedence.

## Commands

| Command | Summary |
| --- | --- |
| `probe` | Run the health probe (default command). |

`probe` is the default, so a bare `owa-doctor` runs it. The probe checks every
sibling consumer (`owa-cal`, `owa-mail`, `owa-graph`, `owa-doctor`,
`owa-people`, `owa-sched`, `owa-drive`, `owa-todo`) and every profile
`owa-piggy` knows about.

Key flags:

- `--profile <alias>` — probe only this profile (default: all profiles).
- `--audience <name>` — token audience to test (default: `graph`; pass
  `outlook` to verify Outlook REST).
- `--no-tokens` — skip per-profile token probes; only check which CLIs are
  installed and at what version.
- `--pretty` — human-readable table (default: JSON).
- `--debug` / `--verbose` — verbose logs to stderr.

```bash
owa-doctor                              # JSON report
owa-doctor --pretty                     # human-readable table
owa-doctor probe --pretty               # explicit subcommand form
owa-doctor --profile work --pretty      # one profile only
owa-doctor --no-tokens                  # quick install check, no token probes
owa-doctor --audience outlook --pretty  # verify Outlook REST too
```

## Output contract

JSON on stdout by default; diagnostics/prompts/errors on stderr. `--pretty` is
the human-readable opt-in. Exit codes follow the suite taxonomy (see
[security.md](security.md) and [agent-integration.md](agent-integration.md)),
with this tool's own probe semantics layered on top:

- `0` — all probed profiles ok
- `1` — one or more profiles near expiry (< 10 min remaining)
- `2` — one or more profiles failed, or `owa-piggy` is missing

## Machine / agent surface

Every owa binary exposes the same machine surface:

- `owa-doctor schema [<command>]` — JSON command schema (one command if named)
- `owa-doctor --help --json` — same schema via the help flag
- `--agent` — wrap JSON stdout in a stable `{"_owa": ..., "data": ...}` envelope (or `OWA_AGENT=1`)
- `--err-json` — structured JSON errors on stderr (or `OWA_ERR_JSON=1`)
- `--doctor [--json]` — this tool's health / redaction doctor payload

See [agent-integration.md](agent-integration.md) for the full contract.

## Caveats

- owa-doctor owns no auth state — it only shells out to `owa-piggy` and the
  sibling CLIs. A missing or broken `owa-piggy` shows up as exit `2`.
- All suite binaries ship at one version (the `version` field is identical
  across siblings); a mismatch in the report means an install is stale.
- `--no-tokens` makes no network calls and never touches a profile, so it is
  the fast way to confirm an install without contacting Microsoft.
