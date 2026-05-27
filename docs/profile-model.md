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
