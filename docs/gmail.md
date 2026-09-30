# owa-gmail

Read-only Gmail CLI. Lists and searches messages, shows one message (headers,
plain/HTML bodies, attachment metadata), downloads the original `.eml` or an
attachment, and lists labels. It never sends, modifies or deletes mail.

## Auth

Gmail is read through an owa-piggy Google profile: a real Google OAuth
Desktop client (client id + secret) consented for `gmail.readonly`. No API
key is involved; every call carries the profile's OAuth bearer token.

```bash
owa-piggy setup --profile brkh-g --google \
  --google-client-id <id>.apps.googleusercontent.com --google-client-secret <secret>
```

With exactly one Google profile, `owa-gmail` picks it; otherwise pass
`--profile <alias>` or pin one with `owa-gmail config --profile <alias>`.
`-A` fans out across Google profiles only. Pointing it at a Microsoft profile
exits `2` ("not a Google profile").

## Commands

```bash
owa-gmail messages --unread --pretty
owa-gmail messages --label inbox --max-results 10
owa-gmail messages --from boss@example.com --since 2026-09-01 --with-body
owa-gmail messages --search "has:attachment larger:5M" --all
owa-gmail show 1a0f38f0c80a6be4 --pretty
owa-gmail get 1a0f38f0c80a6be4 --out mail.eml
owa-gmail attachments 1a0f38f0c80a6be4 <attachment-id> --out logo.png
owa-gmail labels --pretty
owa-gmail refresh
owa-gmail config --profile brkh-g
```

- `owa-gmail messages` lists newest first across every label except spam and
  trash (scheduled sends dated in the future come first; add
  `--label inbox` for the inbox). Filters: `--from`, `--to`, `--subject`,
  `--label`, `--unread`, `--has-attachment`, `--since`/`--until`
  (`YYYY-MM-DD`), or `--search <gmail query>` which replaces them all.
  `--max-results` is the page size (default 25, max 500); when more pages
  exist the JSON is `{"messages": [...], "next_page_token": "..."}` and
  `--page-token` continues. `--all` follows every page and returns a plain
  list. Gmail's list returns only ids, so each row costs one extra call;
  `--with-body` makes that call fetch the full message.
- `owa-gmail show <id>` prints `id, thread_id, label_ids, snippet,
  internal_date_ms, subject, from, to, cc, date, message_id, body_plain,
  body_html, attachments[{filename, mime_type, attachment_id, size}]`.
- `owa-gmail get <id>` writes the original RFC 822 bytes; `owa-gmail attachments
  <message-id> <attachment-id>` writes one attachment. Both go to stdout
  unless `--out <file>` is given, and refuse to overwrite an existing file
  (exit `15`) without `--force`. They cannot fan out across profiles.
- `owa-gmail labels` prints `{id, name, type}` rows, system labels first.
- `owa-gmail refresh` verifies auth and prints the account address;
  `owa-gmail config` shows or pins the default profile.

## Errors

The suite exit codes apply: `11` auth expired (re-run owa-piggy setup for the
Google profile), `13` unknown message or attachment id, `14` rate limited.
Gmail sometimes reports quota exhaustion as a `403`, which surfaces as `12`.
