# Security model for owa-doctor

## TL;DR

`owa-doctor` is a personal productivity tool that probes the user's
own machine for health of the `owa-*` suite. It holds no secrets,
makes no outbound network calls of its own, and writes no files.
Don't deploy it for other people.

## What this actually is

`owa-doctor` runs `owa-piggy` and sibling `owa-*` CLIs as
subprocesses, parses their stdout, and reports a structured
diagnosis. It does decode the access tokens it receives back from
`owa-piggy token` to read the `exp` and `aud` claims for reporting,
but it never persists them, transmits them, or logs them.

## Threat model

**In scope:** single-user, single-machine use. The caller runs
`owa-doctor` under their own account.

- `owa-doctor` does not write any files. It owns no on-disk config.
- Access tokens received from `owa-piggy` are held in memory for
  the duration of one report and then discarded.
- The JSON report includes the token's audience and minutes
  remaining, but **never the token itself**. Capture this output
  freely.
- `--debug` may print probe argv to stderr. The argv contains
  profile aliases but no secrets.

**Out of scope:** multi-user shared installs, deploying as a
service, reading another user's profile data.

## What `owa-doctor` will never do

- Write a config file, log file, or cache.
- Make a direct network call. (The token probe goes through
  `owa-piggy`, which owns the network call.)
- Print an access token to stdout or stderr.
- Persist any per-profile state.

## Reporting issues

If you find a way to exfiltrate token material via `owa-doctor`'s
output, please open a private security advisory on GitHub.
