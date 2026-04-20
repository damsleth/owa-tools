# Security model for cal-cli

## TL;DR

`cal-cli` is a personal productivity tool that reads and writes the
user's own Outlook calendar from the terminal. It uses the user's own
refresh token, stored on disk under the user's own home directory.
Don't deploy it for other people.

## What this actually is

`cal-cli` is a thin client over the Outlook REST API v2. It exchanges
a refresh token for a short-lived access token, then issues
calendarView, events, and masterCategories calls as the authenticated
user. Token acquisition is delegated: either to an app-registration
`client_id` the user controls (via `OUTLOOK_APP_CLIENT_ID`) or to
[`owa-piggy`](../owa-piggy), which the user installs separately.

## Threat model

**In scope:** single-user, single-machine use. The caller runs
`cal-cli` under their own account against their own tenant.

- Refresh tokens are stored at `~/.config/cal-cli/config`, mode
  `0600`. Any process running as that user can read the file. That
  is the same trust boundary SSH keys live in.
- Refresh tokens rotate on every successful exchange; cal-cli
  persists the rotated token back atomically (temp file + fsync +
  rename). A crash mid-exchange leaves either the old or the new
  token, never a truncated mix.
- Access tokens are held in memory only. They are not cached on
  disk; each CLI invocation exchanges the refresh token fresh.
  (`owa-piggy` does cache access tokens; see its SECURITY.md.)
- `config` output deliberately reports "set" / "not set" instead of
  echoing token values.

**Out of scope:**

- Multi-tenant deployment. There is none.
- Service accounts, daemons, or CI secret stores. Do not use this
  tool to schedule automated calendar writes from non-human
  principals.
- Sharing the config file across hosts or users. The token inside
  is a user credential.

## What `cal-cli` does _not_ do

- Register an application in anyone's tenant.
- Send telemetry, crash reports, or update checks. The only
  outbound network calls are:
  - `POST https://login.microsoftonline.com/.../token` (token
    refresh, via the app-registration path only - the `owa-piggy`
    path makes the call from that tool's process).
  - `{GET,POST,PATCH,DELETE} https://outlook.office.com/api/v2.0/...`
    for calendar operations.
- Ask for admin consent.
- Read or write files outside `~/.config/cal-cli/`.

## What _can_ break

- The Outlook REST v2 endpoint (`outlook.office.com/api/v2.0`) is
  older than Graph. Microsoft may EOL it; if that happens, the
  fix is swapping `api_base` to Graph and flipping `api_case` to
  `camel`. The code is already shaped to allow that without a
  rewrite.
- If you use the `owa-piggy` path, every failure mode from
  `owa-piggy`'s SECURITY.md applies here. Read that doc.

## Don't deploy this for other people

If you are thinking _"I could wrap this in a service so the team can
share a calendar bot"_ - don't. The refresh token is a user
credential. Packaging the CLI so a teammate installs it on their own
laptop, using their own Outlook session, is fine. Running it as a
daemon that writes to N calendars on behalf of other people is not.

## Reporting issues

This repo has one user. If you find a real security problem (local
privilege escalation via the config file, token exfiltration through
an error path, etc.), open a GitHub issue or email the address in the
commit log.
