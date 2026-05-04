# Security model for owa-people

## TL;DR

`owa-people` is a personal productivity tool that reads people and
contact data from the user's own Outlook/M365 tenant. It holds no
secrets - only an optional profile alias - and `owa-piggy` owns the
refresh token. Don't deploy it for other people.

## What this actually is

`owa-people` is a thin client over Microsoft Graph. It exchanges a
short-lived access token (via `owa-piggy`) for read access to
`/me/people`, `/users`, `/me/contacts`, and `/me`. It writes nothing
back to Graph today.

## Threat model

**In scope:** single-user, single-machine use. The caller runs
`owa-people` under their own account against their own tenant.

- `~/.config/owa-people/config` contains only an alias string
  (`owa_piggy_profile`). No credentials live in `owa-people`.
- Access tokens are held in memory for the duration of one call.
- Search queries are URL-encoded before being passed to Graph;
  ConsistencyLevel: eventual is set only on the search-style
  endpoints that require it.

**Out of scope:** multi-user shared installs, deploying as a
service, querying another user's contacts.

## What `owa-people` will never do

- Write a token to disk or to its config file.
- Make network calls to anything other than
  `https://graph.microsoft.com/v1.0/...` (and `owa-piggy` for token
  acquisition).
- Modify directory data (today). If write commands are added later,
  they will require explicit `--confirm` for any bulk operation.

## Reporting issues

Open a private security advisory on GitHub.
