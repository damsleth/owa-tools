# Security model for owa-mail

## TL;DR

`owa-mail` is a personal productivity tool that reads and writes the
user's own Outlook mailbox from the terminal. owa-mail holds **no**
auth secrets - tokens are owa-piggy's responsibility, scoped to its
profile store. The only thing on disk under `~/.config/owa-mail/` is
an optional profile-alias string. Don't deploy it for other people.

## What this actually is

`owa-mail` is a thin client over the Outlook REST API v2. It asks
[`owa-piggy`](../owa-piggy) for a short-lived access token, then
issues messages, sendMail, mailFolders, move, createReply /
createForward and deferred-send calls as the authenticated user.
Token acquisition is fully delegated to owa-piggy; owa-mail itself
never talks to AAD.

## Threat model

**In scope:** single-user, single-machine use. The caller runs
`owa-mail` under their own account against their own tenant.

- `~/.config/owa-mail/config` contains only an alias string
  (`owa_piggy_profile`). No credentials live in owa-mail. The
  refresh token lives in owa-piggy's profile store and is subject
  to owa-piggy's threat model (see its `SECURITY.md`).
- The config file is chmod `0600` as a hygiene default, even though
  it carries no secrets - it lives under the user's home and there
  is no reason for other users on a shared box to read it.
- Access tokens are held in memory only. They are not cached on
  disk; each CLI invocation asks owa-piggy for a fresh one.
  (`owa-piggy` does cache access tokens in its own process; see its
  SECURITY.md.)

**Out of scope:**

- Multi-tenant deployment. There is none.
- Service accounts, daemons, or CI secret stores. Do not use this
  tool to schedule automated mail sends from non-human principals.
  Mail abuse risk is higher than calendar abuse risk; treat this as
  a hard line.
- Sharing the config file across hosts or users. The token inside
  is a user credential and the mailbox it unlocks is yours.

## What `owa-mail` does _not_ do

- Register an application in anyone's tenant.
- Talk directly to `login.microsoftonline.com`. Token acquisition
  happens in owa-piggy's process, not this one.
- Send telemetry, crash reports, or update checks. The only
  outbound network calls owa-mail makes are
  `{GET,POST,PATCH,DELETE} https://outlook.office.com/api/v2.0/...`
  for mail operations.
- Ask for admin consent.
- Read or write files outside `~/.config/owa-mail/`.
- Render HTML mail (no third-party HTML parser is bundled). HTML
  bodies returned by `show` are printed verbatim; if you pipe that
  to a viewer, sanitise it first.

## Mail-specific risks

- **Sending is irreversible.** A bug in `cmd_send` could send the
  wrong content to the wrong people. The CLI has no built-in dry-run
  flag (use `--save-draft` to inspect a draft before dispatching).
  Never auto-confirm sends in scripts you don't fully trust.
- **Scheduled send sits in your Outbox.** `--send-at` creates a
  deferred-delivery draft. If you delete the draft from another
  client between scheduling and dispatch, the message will not be
  sent. There is no callback mechanism.
- **Reply / forward replies write into your Sent Items folder by
  default.** `SaveToSentItems: true` is hard-coded for the immediate
  send path. If your mailbox policy redirects sent items elsewhere,
  the message still leaves; only the local copy is affected.
- **`delete` is soft-delete** - Outlook moves the message to
  DeletedItems. `move --to DeletedItems` is equivalent. Neither
  bypasses retention policies; do not rely on either to scrub
  evidence.

## What _can_ break

- The Outlook REST v2 endpoint (`outlook.office.com/api/v2.0`) is
  older than Graph. Microsoft may EOL it. A migration to Graph would
  need owa-piggy's SPA client to carry the mail scopes on the Graph
  audience too, which is not guaranteed; that switch belongs in
  owa-piggy first, owa-mail second.
- Every failure mode from `owa-piggy`'s SECURITY.md applies here.
  Read that doc.
- `PR_DEFERRED_SEND_TIME` is a stable MAPI property tag, but
  Microsoft's transport behaviour around it is not contractually
  guaranteed. If a future Exchange change ignores the property,
  scheduled sends would dispatch immediately. Spot-check your
  scheduled sends.

## Don't deploy this for other people

If you are thinking _"I could wrap this in a service so the team can
share a mail bot"_ - don't. The refresh token is a user credential.
Packaging the CLI so a teammate installs it on their own laptop,
using their own Outlook session, is fine. Running it as a daemon
that sends mail on behalf of N other people is not.

## Reporting issues

This repo has one user. If you find a real security problem (local
privilege escalation via the config file, token exfiltration through
an error path, etc.), open a GitHub issue or email the address in
the commit log.
