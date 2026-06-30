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
owa-mail messages --has-attachments --importance high --pretty
owa-mail messages --category Red --skip 25 --limit 25      # page 2 of a category
owa-mail messages --orderby 'Subject asc' --pretty         # custom OData $orderby
owa-mail thread --id AAQkAG... --pretty                    # messages in a conversation
owa-mail read --latest --pretty                      # newest message, full body, no id
owa-mail read -n 2 --from anthropic --pretty         # 2nd newest from a sender
owa-mail show --id AAMkAG... --pretty                # by explicit message id

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
owa-mail move --id AAMkAG... --to "Project X"        # by folder display name
owa-mail copy --id AAMkAG... --to Archive            # copy instead of move
owa-mail categories --id AAMkAG... --category Red --category Urgent
owa-mail categories --id AAMkAG...                   # clear all categories
owa-mail delete --id AAMkAG... --confirm

owa-mail refresh
owa-mail config --profile work
```

Messages carry opaque ids: address one via `--id` or as a bare positional
argument (`owa-mail show <id>` == `owa-mail show --id <id>`). Note that the
`messages` JSON exposes both `id` and `conversation_id`, which look alike;
`show` needs `id`. To skip ids entirely, use `read`.

### read - reading by recency

`read` resolves a single message by *position* instead of id, so you never
have to copy an opaque handle. `--latest` (the default) reads the newest
message; `-n N` / `--index N` reads the N-th newest (1-based). The same
listing filters as `messages` narrow the set first:

```sh
owa-mail read                                  # newest in Inbox (JSON)
owa-mail read --latest --pretty                # newest, human-readable body
owa-mail read -n 3 --pretty                    # 3rd newest
owa-mail read --unread --latest --pretty       # newest unread
owa-mail read --folder SentItems -n 1 --pretty # last thing you sent
```

Like `show`, JSON is the default and `--pretty` flattens HTML to readable
text. URLs in the body are preserved as numbered `[n]` footnotes with a
trailing `Links:` section, so login links and confirmations stay usable.

For an interactive full-screen mail browser, see [owa-tui](https://github.com/damsleth/owa-tui).

### Folder names

The `--folder` and `--to` (move / copy) flags accept these well-known
names (case-insensitive, with common aliases):

| Canonical      | Aliases                |
| -------------- | ---------------------- |
| `Inbox`        |                        |
| `Drafts`       | `draft`                |
| `SentItems`    | `sent`                 |
| `DeletedItems` | `deleted`, `trash`     |
| `JunkEmail`    | `junk`, `spam`         |
| `Outbox`       |                        |
| `Archive`      | `archived`             |

For `move` and `copy`, anything that isn't a well-known name is first
looked up as a folder **display name** (exact, case-insensitive); if no
folder matches it is passed through as an opaque folder id. So
`owa-mail move --id ... --to "Project X"` works without a manual
`folders` lookup. (`--folder` on listings still takes only well-known
names or ids.) Either way you can find an id via
`owa-mail folders | jq '.[] | {name, id}'`.

### Filtering and paging

`messages` adds server-side OData filters on top of `--unread` /
`--from` / `--subject`:

- `--category <name>` - only messages tagged with that category.
- `--has-attachments` - only messages with attachments.
- `--importance low|normal|high` - only messages of that importance.
- `--orderby <field>` - OData `$orderby` passthrough (e.g.
  `--orderby 'Subject asc'`). Overrides the default newest-first order.
- `--skip <n>` - OData `$skip` passthrough for offset paging alongside
  `--limit`.

These compose with each other but, like the other filters, cannot be
combined with `--search` (`$search` and `$filter` are mutually
exclusive in Outlook REST).

### Categories

`categories --id <message-id> --category <name>` sets the categories on
a message. `--category` is repeatable; the supplied list replaces the
message's categories wholesale (idempotent), so passing none clears
them. Filter a listing by category with `messages --category <name>`.

```sh
owa-mail categories --id AAMkAG... --category Red --category Urgent
owa-mail categories --id AAMkAG...                  # clear all
owa-mail messages --category Red --pretty
```

### Threads / conversations

`thread --id <conversation-id>` (alias `conversation`) lists every
message in a conversation, newest first, across all folders. The id is
the `conversation_id` field surfaced in `messages` / `show` JSON (it
starts `AAQk`, not the `AQMk` message `id`).

```sh
owa-mail thread --id AAQkAG... --pretty
owa-mail conversation --id AAQkAG... --all | jq length
```

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

File attachments have a `$value`; **item** attachments (an embedded
message/event) and **reference** attachments (a link to a cloud file)
do not. For those, `attachment-get` falls back to fetching the full
attachment resource and emits its metadata as JSON instead - including
the embedded `item` for item attachments and the `source_url` for
reference attachments - rather than failing.

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
