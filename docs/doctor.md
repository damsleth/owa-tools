# owa-doctor

Health-check meta-CLI for the [`owa-*`](https://github.com/damsleth) suite.

One command, structured report: which CLIs are installed, which
[`owa-piggy`](https://github.com/damsleth/owa-piggy) profiles can
still mint a token, and which are about to expire.

```
$ owa-doctor --pretty
owa-piggy: ok (0.7.1) at /opt/homebrew/bin/owa-piggy

Siblings:
  cli         state    version
  owa-cal     ok       0.6.2
  owa-mail    ok       0.1.1
  owa-graph   ok       0.2.0
  owa-people  missing  -
  owa-sched   missing  -
  owa-drive   missing  -

Profiles (audience=graph):
  alias    default  state  mins-left  note
  brkh              ok     78
  crayon            fail   -          AADSTS70043 refresh token expired
  dno               ok     77
  swon     yes      ok     72

Summary: 3 ok, 0 warn, 1 fail
```

Exit codes:

- `0` - all probed profiles ok
- `1` - one or more profiles near expiry (< 10 min remaining)
- `2` - one or more profiles failed, or `owa-piggy` is missing

## Install

```bash
pipx install owa-doctor    # once published
# or, from a clone:
pipx install .
```

## Usage

```bash
owa-doctor                              # JSON report
owa-doctor --pretty                     # human-readable table
owa-doctor --profile swon --pretty      # one profile only
owa-doctor --no-tokens                  # quick install check, no token probes
owa-doctor --audience outlook --pretty  # verify Outlook REST too
owa-doctor probe --no-tokens            # explicit subcommand form
```

`owa-doctor` shells out to `owa-piggy` and sibling CLIs. It owns no
auth state of its own.

## License

MIT
