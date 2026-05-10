# Profile model

Every consumer tool delegates auth to `owa-piggy`. Profiles are how you switch identities (work, personal, multi-tenant) without juggling separate token caches.

## Where profiles live

`owa-piggy` owns the profile store. Tools never touch refresh tokens.

```
~/.config/owa-piggy/
  config            # profile aliases and defaults
  tokens/
    default.json    # encrypted token bundle for the default profile
    work.json       # encrypted token bundle for "work"
    personal.json
    ...
```

Consumer tools store at most an alias name (e.g., `owa_piggy_profile=work` in `~/.config/owa-cal/config`). They forward the alias to `owa-piggy` as `--profile work`, and `owa-piggy` returns an access token for the right identity.

## Setup

```bash
# First-time, default profile
owa-piggy setup

# Named profile
owa-piggy --profile work setup
```

Setup is interactive and requires a browser. Subsequent token refreshes are non-interactive.

## Selection precedence

When a consumer tool resolves which profile to use, in order:

1. `--profile <alias>` flag on the command line.
2. `OWA_PIGGY_PROFILE` environment variable.
3. Tool's persisted config (`~/.config/<tool>/config`, key `owa_piggy_profile`).
4. `owa-piggy`'s default profile.

This matches the precedence used by every consumer tool today.

## Pinning a tool to a profile

```bash
# Make `owa-cal` always use the "work" profile, no matter what
# OWA_PIGGY_PROFILE is set to.
owa-cal config --profile work
```

Each tool has its own `config --profile <alias>` subcommand for this.

## Multi-tenant tip

If you work across multiple tenants, set up one `owa-piggy` profile per tenant and use the env var per shell:

```bash
# In your work shell
export OWA_PIGGY_PROFILE=acme

# In your personal shell
export OWA_PIGGY_PROFILE=personal
```

The consumer tools pick up the env var automatically.

## Audience and scope

`owa-piggy` profiles are tenant-scoped, not audience-scoped. The suite uses two audiences:

- `outlook` (Outlook REST). Used by `owa-cal`, `owa-mail`.
- `graph` (Microsoft Graph). Used by `owa-graph`, `owa-people`, `owa-sched`, `owa-drive`, parts of `owa-doctor`.

Each profile carries scopes for both audiences. The token cache is keyed on `(profile, audience)`, so switching tools inside the same profile does not re-prompt for consent.

## Health checks

```bash
owa-piggy whoami            # which identity is active
owa-piggy whoami --json     # same, machine-readable
owa-doctor probe            # full suite health (every tool, every audience)
```

`owa-doctor probe --no-tokens` runs without invoking `owa-piggy` at all; useful for CI on a machine that doesn't have any seeded profiles.

## Coming from per-tool installs

Profile resolution is unchanged from the legacy per-tool releases. If you
are migrating from the old standalone `owa-cal` / `owa-mail` / etc.
installs, see `docs/migrating-from-individual-installs.md` for the install
swap. Your existing `~/.config/owa-piggy/` and per-tool
`~/.config/<tool>/config` files keep working as is.
