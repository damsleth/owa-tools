# Security model for owa-drive

## TL;DR

`owa-drive` is a personal productivity tool that reads, writes, and
deletes files in the user's own OneDrive. It holds no secrets -
only an optional profile alias - and `owa-piggy` owns the refresh
token. Don't deploy it for other people.

## What this actually is

`owa-drive` is a thin client over Microsoft Graph `/me/drive`.
It exchanges a short-lived access token (via `owa-piggy`) for
read+write access to the caller's own OneDrive: list folders,
download/upload files, delete items.

## Threat model

**In scope:** single-user, single-machine use. The caller runs
`owa-drive` under their own account against their own tenant.

- `~/.config/owa-drive/config` contains only an alias string.
  No credentials.
- Access tokens are held in memory for one call.
- File content downloaded with `get` is written to disk only when
  `--out <path>` is set; otherwise it streams to stdout. The user
  is responsible for not piping it to a malicious target.
- Uploads (`put`) read the local file once and PUT it. Files
  larger than 4 MB are rejected client-side; the server enforces
  its own limits.

**Out of scope:** multi-user shared installs, deploying as a
service, accessing another user's drive.

## What `owa-drive` will never do

- Write a token to disk.
- Delete the drive root (`paths.delete_endpoint('')` raises;
  `cmd_rm` short-circuits).
- Modify items without `--confirm` (or interactive `yes`).
- Sync entire folders. This is an explicit-call CRUD tool, not a
  sync client.

## Reporting issues

Open a private security advisory on GitHub.
