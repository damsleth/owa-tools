# owa-mail

Mail CLI for Outlook / Microsoft 365. Read, send, schedule, reply,
forward, move, mark and delete mail from the terminal.
Pipe-friendly JSON by default, `--pretty` for humans.

```sh
brew install damsleth/tap/owa-tools      # ships owa-mail + the whole suite
owa-mail messages --pretty
```

Or one-shot, no install, no on-disk state:

```sh
OWA_REFRESH_TOKEN=1.AQ... OWA_TENANT_ID=<tenant-id-or-domain> \
  uvx --from owa-tools owa-mail messages --pretty
```

`uvx --from owa-tools` pulls the suite (and owa-piggy as a transitive
dep) into a throwaway venv. The two env vars feed straight through to
owa-piggy's env-only mode - nothing is written to `~/.config/`.

---

## Happy-path setup (no app registration)

[`owa-piggy`](https://github.com/damsleth/owa-piggy) owns the token
lifecycle; owa-mail just shells out to it on every call. The full
first-run flow:

```sh
# 1. Install both
brew install damsleth/tap/owa-piggy damsleth/tap/owa-tools

# 2. Seed owa-piggy once from your browser (walks you through it)
owa-piggy setup

# 3. Go
owa-mail messages --pretty
```

owa-piggy and owa-tools version independently. owa-mail expects any
owa-piggy >= 0.7.1 and sanity-checks the version on first call.

Multi-account: seed a named owa-piggy profile and pin it in owa-mail's
config.

```sh
owa-piggy setup --profile work
owa-mail config --profile work
```

`--profile` also works as a one-shot override:
`owa-mail --profile home messages`.

---

## The output contract

**JSON on stdout, logs on stderr.** Every read command emits parseable
JSON by default; `--pretty` is a human override that goes to stdout
too. The entire CLI composes with `jq`:

```sh
owa-mail messages --limit 5
```

```json
[
  {
    "id": "AAMkAG...",
    "conversation_id": "...",
    "received": "2026-04-30T08:42:11Z",
    "subject": "Hello",
    "from": "alice@example.com",
    "to": "me@example.com",
    "cc": "",
    "preview": "Just checking in...",
    "is_read": false,
    "has_attachments": false,
    "importance": "Normal",
    "flag": "NotFlagged",
    "folder_id": "AAA...",
    "web_link": "https://outlook.office.com/..."
  }
]
```

Field names in the output are stable lowercase; the backend is Outlook
REST v2 (PascalCase upstream) but owa-mail hides that detail.

```sh
owa-mail messages --unread | jq '.[] | "\(.from): \(.subject)"'
owa-mail messages --since 2026-04-01 | jq '[.[] | select(.has_attachments)] | length'
owa-mail folders | jq '.[] | select(.unread > 0)'
```

`messages` and `folders` cap at a single page by default. Pass `--all`
to follow `@odata.nextLink` until the collection is exhausted; `--limit`
still controls the page size requested per round-trip. Output shape is
unchanged (a JSON array, or a `--pretty` table over all rows).

```sh
owa-mail messages --since 2026-01-01 --all | jq length
owa-mail folders --all --pretty
```

`show` returns a single message object (with `body` and `body_type`
fields included). In JSON mode the `body` is emitted verbatim - if Graph
returned an HTML body (`body_type: "html"`, the common case) you get the
raw markup, unchanged. With `--pretty`, HTML bodies are flattened to
readable plain text using a stdlib `html.parser`-based converter: block
elements become line breaks, list items get `- ` bullets, `<script>` and
`<style>` content is dropped, entities (`&amp;`, `&nbsp;`, `&#39;`, ...)
are unescaped, and runs of whitespace/blank lines are collapsed. Links
keep their visible text only. Text bodies (`body_type: "text"`) pass
through unchanged in both modes.

`send`/`reply`/`forward` return `{"sent": true,
"id": "...", "send_at": null|"<iso>"}`. `mark`/`move` return the
updated message resource. `delete` writes `Deleted.` to stderr.
`attachments` returns an array of attachment metadata objects (no
base64 content); `attachment-get` writes the raw attachment bytes to
stdout or `--out`.

---

## Commands

```sh
# Read
owa-mail messages --pretty                           # Inbox, last 25
owa-mail messages --unread --limit 10 --pretty
owa-mail messages --folder SentItems --since 2026-04-01 --pretty
owa-mail messages --search 'subject:invoice'         # KQL search
owa-mail show --id AAMkAG... --pretty

# Attachments (read)
owa-mail attachments --id AAMkAG... --pretty            # list a message's attachments
owa-mail attachment-get --id AAMkAG... --attachment AAA... --out ./report.pdf
owa-mail attachment-get --id AAMkAG... --attachment AAA... > report.pdf

# Send
owa-mail send --to a@example.com --subject "hi" --body "hello"
owa-mail send --to a@b.c,c@d.e --cc x@y.z --subject "review" --body "..." --html
owa-mail send --to a@b.c --subject "later" --body "..." --send-at 2026-05-01T09:00:00Z
owa-mail send --to a@b.c --subject "draft" --body "..." --save-draft
owa-mail send --to a@b.c --subject "report" --body "see attached" --attach ./report.pdf
echo "body from pipe" | owa-mail send --to a@b.c --subject "piped" --body -

# Threads
owa-mail reply --id AAMkAG... --body "thanks"
owa-mail reply-all --id AAMkAG... --body "thanks all"
owa-mail forward --id AAMkAG... --to friend@example.com --body "fyi"
owa-mail forward --id AAMkAG... --to friend@example.com --attach ./slides.pdf

# Mailbox
owa-mail folders --pretty
owa-mail mark --id AAMkAG... --read
owa-mail mark --id AAMkAG... --flag
owa-mail move --id AAMkAG... --to Archive
owa-mail delete --id AAMkAG... --confirm

owa-mail refresh
owa-mail config --profile work
```

Messages carry opaque ids: address one via `--id` or as a bare positional
argument (`owa-mail show <id>` == `owa-mail show --id <id>`).

### Folder names

The `--folder` and `--to` (move) flags accept these well-known names
(case-insensitive, with common aliases):

| Canonical      | Aliases                |
| -------------- | ---------------------- |
| `Inbox`        |                        |
| `Drafts`       | `draft`                |
| `SentItems`    | `sent`                 |
| `DeletedItems` | `deleted`, `trash`     |
| `JunkEmail`    | `junk`, `spam`         |
| `Outbox`       |                        |
| `Archive`      | `archived`             |

Anything else is treated as an opaque folder id (look one up via
`owa-mail folders | jq '.[] | {name, id}'`).

### Scheduled send

`--send-at` accepts an ISO datetime. Naive values are interpreted as
UTC; offsets are converted to UTC before being attached to the draft.

```sh
owa-mail send --to a@b.c --subject "later" --body "..." --send-at 2026-05-01T09:00:00Z
owa-mail send --to a@b.c --subject "later" --body "..." --send-at 2026-05-01T09:00:00+02:00
```

Behind the scenes owa-mail creates a draft, attaches the
`PR_DEFERRED_SEND_TIME` extended property, and dispatches it to
`/send`. Exchange Transport then holds the message in your Outbox
until the scheduled time - the same mechanism OWA's "Schedule send"
button uses.

### Attachments

**Reading.** `attachments --id <message-id>` lists a message's
attachments as JSON (or a table with `--pretty`); each row carries
`id`, `name`, `content_type`, `size`, `kind` (`fileAttachment` /
`itemAttachment` / `referenceAttachment`) and `is_inline`. The listing
never includes the base64 content. Use the `id` to download one file
attachment with `attachment-get`:

```sh
owa-mail attachments --id AAMkAG...                          # JSON
owa-mail attachments --id AAMkAG... --pretty                 # table
owa-mail attachment-get --id AAMkAG... --attachment AAA... --out ./report.pdf
owa-mail attachment-get --id AAMkAG... --attachment AAA... > report.pdf
```

`attachment-get` streams the raw bytes to stdout by default (use it
with a redirect or pipe), or writes them to `--out <path>`. It fetches
the attachment's `$value` endpoint, so the bytes are exactly as stored.

**Sending.** `--attach <file>` is repeatable and works on `send`,
`reply`, `reply-all`, and `forward`:

```sh
owa-mail send --to a@b.c --subject hi --body "see files" \
  --attach ./a.pdf --attach ./b.png
owa-mail reply --id AAMkAG... --body "as discussed" --attach ./notes.txt
owa-mail forward --id AAMkAG... --to c@d.e --attach ./slides.pdf
```

Files **3 MB or smaller** are sent inline in the message (base64 in
the `Attachments` array). Files **larger than 3 MB** transparently use
a Microsoft Graph **upload session**: owa-mail creates a draft (or, for
reply/forward, uses the createReply/createForward draft), POSTs a
`createUploadSession` for each large file, PUTs the bytes in chunks to
the pre-authorized `uploadUrl`, then sends the draft. Small no-attachment
and small-inline sends keep using the single-shot `sendMail` action, so
nothing about the existing fast path changes.

---

## Machine / agent surface

Every owa binary exposes the same machine surface (see
[agent-integration.md](agent-integration.md) for the full contract):

- `owa-mail schema [<command>]` - JSON command schema (one command if named)
- `owa-mail --help --json` - the same schema via the help flag
- `--agent` - wrap JSON stdout in a stable `{"_owa": ..., "data": ...}`
  envelope (or set `OWA_AGENT=1`)
- `--err-json` - structured JSON errors on stderr (or `OWA_ERR_JSON=1`)
- `--doctor [--json]` - this tool's health / redaction doctor payload

---

## Auth

owa-mail shells out to
[`owa-piggy`](https://github.com/damsleth/owa-piggy) for an access
token on every call. owa-piggy piggybacks on OWA's public SPA client,
so no app registration is needed; owa-mail itself stores no token.
Optional `owa_piggy_profile` pins a named owa-piggy profile.

If you have your own app registration and would rather use it, that
goes through owa-piggy too - owa-mail is a token consumer, not a
token acquirer.

Config lives at `~/.config/owa-mail/config`:

```
# Optional - pins which owa-piggy profile to consume tokens from
owa_piggy_profile="work"
```

---

## Dependencies

- Python 3.10+
- [`owa-piggy`](https://github.com/damsleth/owa-piggy) >= 0.7.1

## Development

owa-mail ships in the `owa-tools` suite repository:

```sh
git clone https://github.com/damsleth/owa-tools
cd owa-tools
python -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest -q
```

Live mailbox tests are opt-in and hit a real Outlook account through
`owa-piggy`. Set the live profile alias and recipient explicitly, and
optionally override the Python interpreter used for `-m owa_mail`:

```sh
OWA_MAIL_LIVE=1 OWA_MAIL_LIVE_PROFILE=work OWA_MAIL_LIVE_TO=me@example.com \
  python -m pytest -q src/tests/mail/test_live.py
OWA_MAIL_LIVE=1 OWA_MAIL_LIVE_PROFILE=work OWA_MAIL_LIVE_TO=me@example.com \
  OWA_MAIL_LIVE_PYTHON=python3 python -m pytest -q src/tests/mail/test_live.py
```

See [`AGENTS.md`](../AGENTS.md) for repo layout and ground rules.

## What's not in this version

- **Real-time receive** (webhooks, IMAP IDLE) - poll `messages
  --unread` from cron or your agent loop.

## Disclaimer

```
Personal tooling. owa-mail holds no auth secrets of its own -
tokens are owa-piggy's responsibility, scoped to its profile store.
If you don't know why piping a real mailbox through a personal CLI
might be a bad idea, don't use it.
```
