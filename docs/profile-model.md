# Profile model

Every consumer tool delegates auth to `owa-piggy`. Profiles are how you switch
identities (work, personal, multi-tenant) without juggling separate token
caches.

## Where profiles live

`owa-piggy` owns the profile store. Consumer tools never touch refresh tokens
and never read `~/.config/owa-piggy` directly - they only call the `owa-piggy`
subprocess JSON surface.

```
~/.config/owa-piggy/
  profiles.conf              # default alias + registered aliases (0600)
  profiles/
    default/
      config                 # plaintext key=value, refresh token included (0600)
    work/
      config
    personal/
      config
    ...
```

Token material is stored as plaintext at file mode `0600` (owner read/write
only) - it is not an encrypted bundle. Short-lived access tokens are cached
per profile (also `0600`) so back-to-back calls don't re-hit the token
endpoint.

Consumer tools store at most an alias name (e.g. `owa_piggy_profile=work` in
`~/.config/owa-cal/config`). They forward the alias to `owa-piggy` as
`--profile work`, and `owa-piggy` returns an access token for the right
identity.

## Setup

```bash
# First-time, default profile
owa-piggy setup

# Named profile (subcommand first, then flags)
owa-piggy setup --profile work --email you@example.com
```

Setup is interactive and requires a browser. Subsequent token refreshes are
non-interactive.

## Selection precedence

When a consumer tool resolves which profile to use, in order:

1. `--profile <alias>` flag on the command line.
2. `OWA_PROFILE` environment variable.
3. Tool's persisted config (`~/.config/<tool>/config`, key `owa_piggy_profile`).
4. `owa-piggy`'s default profile.

This matches the precedence used by every consumer tool today. Note the env var
is `OWA_PROFILE`; `owa_piggy_profile` is the *config-file key*, not an env var.

## Pinning a tool to a profile

```bash
# Make `owa-cal` always use the "work" profile, no matter what
# OWA_PROFILE is set to.
owa-cal config --profile work
```

Each tool has its own `config --profile <alias>` subcommand for this.

## Fan-out across profiles

Pass `--profile` **more than once** and the command runs against each profile in
a single invocation, merging the results keyed by profile. Zero or one
`--profile` behaves exactly as it always has - the fan-out shape only appears
for two or more.

```bash
owa-mail  --profile crayon --profile brkh messages --unread
owa-graph --profile crayon --profile dno GET /me
owa-cal   --profile crayon --profile swon events --pretty
```

The flag is order-preserving and de-duplicated: a repeated alias warns once on
stderr (`warning: duplicate --profile <v> ignored`) and is dropped, so
`--profile a --profile a` collapses to the single-profile path.

### Fan out across *every* profile (`--profile all`)

`all` is a reserved meta-profile that expands to every eligible profile, so you
don't have to spell them out:

```bash
owa-cal   events --pretty --profile all
owa-graph GET /me --all-profiles
owa-mail  messages --all-profiles
owa-todo  tasks -A
```

Three equivalent spellings: `--profile all`, the long alias `--all-profiles`,
and the short alias `-A`. They all normalize to the same thing.

- **Scope.** "Eligible" means **active and configured** — a profile registered
  with `owa-piggy` that has a stored config. Inactive or config-less profiles
  are not part of `all`.
- **Reserved name.** No profile may be named `all`; if one is (e.g. a
  hand-edited store), the command fails with a usage error rather than guessing.
- **Shape follows intent, not count.** An explicit `all` request always produces
  the profile-keyed `results` shape — even when it resolves to a single profile
  — so scripts and agents never special-case "one profile came back flat".
- **No eligible profiles** → usage error (`run owa-piggy login first`).
- `all` composes with explicit aliases: `--profile work --profile all` keeps
  `work` first, then appends the rest, de-duplicated.

### Output shapes

- **JSON (default):** an envelope with a `results` array, one entry per profile.
  Each entry is `{"profile", "ok", "data"}` on success or `{"profile", "ok":
  false, "error", "exit_code"}` on failure. The `_owa` meta carries the
  `profiles` list.

  ```json
  {
    "_owa": {"suite": "owa-tools", "tool": "owa-mail", "command": "messages",
             "profiles": ["crayon", "brkh"]},
    "results": [
      {"profile": "crayon", "ok": true, "data": [ ... ]},
      {"profile": "brkh",   "ok": false, "error": "token expired", "exit_code": 11}
    ]
  }
  ```

- **`--pretty`:** one labelled section per profile, `=== profile: <alias> ===`
  (a failed profile gets `=== profile: <alias> (FAILED) ===` plus its error).
- **`--ndjson`:** every line is tagged with its profile - `{"profile": ...,
  "item": ...}` - so `jq` can split a merged stream back apart.

### Per-profile isolation and exit codes

Each profile is run independently; one profile's auth failure or error never
aborts the others. The overall exit code reflects the set:

| Outcome | Exit code |
|---|---|
| All profiles succeeded | `0` |
| Some succeeded, some failed | `2` |
| All profiles failed | `1` |

### What can't fan out

Interactive commands (a curses `tui` is one terminal, not N) and binary-output
commands (e.g. `owa-drive get` writing a file to stdout) are refused with a
usage error when more than one `--profile` is given - run them once per
`--profile` instead. `owa-doctor` opts out of fan-out entirely: its `--profile`
selects which single profile to probe, and bare `owa-doctor` already probes
every profile in one pass.

### `OWA_PROFILE` vs repeated `--profile`

`OWA_PROFILE` is **single-valued** - it names one fallback profile for the
session and never fans out. Fan-out is a flag-only feature: the repeated
`--profile` flags win over `OWA_PROFILE` (per the precedence above) and are the
only way to target several profiles at once.

## Multi-tenant tip

If you work across multiple tenants, set up one `owa-piggy` profile per tenant
and use the env var per shell:

```bash
# In your work shell
export OWA_PROFILE=acme

# In your personal shell
export OWA_PROFILE=personal
```

The consumer tools pick up the env var automatically.

## Audience and scope

`owa-piggy` profiles are tenant-scoped, not audience-scoped. The suite uses two
audiences in practice:

- `outlook` (Outlook REST). Used by `owa-cal`, `owa-mail`, `owa-todo`.
- `graph` (Microsoft Graph). Used by `owa-graph`, `owa-people`, `owa-sched`,
  `owa-drive`, and `owa-doctor`.

A single profile can mint tokens for both audiences. The access-token cache is
keyed by `(tenant, client, scope)` within each profile's directory, so
switching tools inside the same profile reuses cached tokens instead of
re-prompting.

`owa-piggy` accepts more audiences than the suite uses (`teams`, `azure`,
`keyvault`, ... — see `owa-piggy` for the full list); `owa-graph --audience
<name>` forwards any of them.

## Health checks

```bash
owa-piggy status            # which identities are active, ISO8601 summary
owa-piggy status --json     # same, machine-readable
owa-doctor probe            # full suite health (every tool, every audience)
```

`owa-doctor probe --no-tokens` runs without invoking `owa-piggy` at all; useful
for CI on a machine that doesn't have any seeded profiles.
