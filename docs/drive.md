# owa-drive

OneDrive CRUD CLI for Outlook / Microsoft 365.

Pipe-friendly OneDrive CRUD. JSON metadata on stdout, file content on stdout
for `get`, `--pretty` for humans. Sibling of `owa-cal` / `owa-mail` /
`owa-people` / `owa-sched`.

```
$ owa-drive ls /Documents --pretty
kind  size    modified              name
d     -       2026-04-30 09:12:00   Projects
f     1.2M    2026-05-01 14:00:00   Q1 plan.docx
f     45K     2026-05-04 08:30:00   notes.md

$ owa-drive get /Documents/notes.md --out ./notes.md
wrote 46123 bytes to ./notes.md

$ cat report.md | owa-drive put - /Documents/report.md
{"id":"...","name":"report.md","kind":"file","size":2014,...}

$ owa-drive rm /Documents/old.txt --confirm
deleted: /Documents/old.txt
```

## Install

Part of the `owa-tools` suite — one install gives you all nine binaries plus the `owa-piggy` auth broker:

```bash
brew install damsleth/tap/owa-piggy damsleth/tap/owa-tools
# or: pipx install owa-piggy && pipx install owa-tools
```

Run as `owa-drive ...` or via the umbrella `owa drive ...`.

## Auth

owa-drive shells out to `owa-piggy` for a fresh access token on every call;
`owa-piggy` owns the refresh token and profile registry. Audience: graph.

```bash
owa-piggy setup --profile work        # one-time, opens a browser
```

See [profile-model.md](profile-model.md) for profile precedence.

## Commands

| Command (alias) | Summary |
| --- | --- |
| `ls [path]` (`list`) | List a folder (default: drive root). |
| `show <path>` | Show metadata for one item. |
| `get <path>` (`download`) | Download file content (stdout, or `--out <local>`). |
| `put <local> <remote-path>` (`upload`) | Upload a file of any size (`-` reads stdin). Refuses to overwrite without `--force` (exit 15). |
| `put <local>… <remote-dir>` (batch) | Upload many files to a directory; existing files are skipped, per-file failures don't abort the batch. `--force` overwrites. |
| `rm <path>` (`delete`) | Delete an item (requires `--confirm`). |
| `refresh` | Force a token refresh and verify auth. |
| `config` | View or update configuration. |

The four CRUD verbs use unix-style names as the primary form, and the
suite-canonical verbs are accepted as aliases for the same operation:
`ls`/`list`, `get`/`download`, `put`/`upload`, `rm`/`delete`. Either name
works on the command line.

Common flags: `--pretty` (human-readable table for `ls` / `show`), `--all`
(follow `@odata.nextLink` until exhausted, `ls`), `--out <local>` (write a
download to a file instead of stdout, `get`), `--confirm` (skip the prompt,
`rm`), and `--profile <alias>` (forward to `owa-piggy` for one invocation).

```bash
owa-drive ls --pretty                          # drive root
owa-drive ls "/Documents" --pretty
owa-drive ls "/Documents" --all | jq length
owa-drive list "/Documents" --pretty           # alias for ls
owa-drive show "/Documents/Q1 plan.docx" --pretty
owa-drive get "/Documents/notes.md" --out ./notes.md
owa-drive download "/Documents/notes.md" | jq .   # alias for get
cat ./report.md | owa-drive put - "/Documents/report.md"
owa-drive upload ./foo.txt "/Documents/foo.txt"   # alias for put
owa-drive rm "/Documents/old.txt" --confirm
owa-drive delete "/Documents/old.txt" --confirm   # alias for rm
owa-drive refresh
owa-drive config --profile acme
```

`ls` returns a single page by default. Pass `--all` to follow
`@odata.nextLink` until the folder is fully enumerated (handy for large
folders). Output shape is unchanged (a JSON array, or a `--pretty` table over
all rows).

### Uploads

`put` handles files of any size. Files at or under 4 MB upload in a single
`PUT`. Larger files transparently use a Microsoft Graph resumable upload
session: the bytes are streamed to a pre-authorized upload URL in sequential
chunks (a multiple of 320 KiB each). The whole payload is read into memory
before upload, so a multi-GB file needs comparable RAM.

```bash
owa-drive put ./big-video.mp4 /Documents/big-video.mp4
# uploading 734003200 bytes via upload session...
# {"id":"...","name":"big-video.mp4","kind":"file","size":734003200,...}
```

### Overwrite handling and batch upload

`put` refuses to overwrite an existing remote item by default and exits with
code `15` (CONFLICT). OneDrive enables file-version history on every drive,
so the refusal is a bandwidth optimization — it lets `put` skip the upload
bytes when the remote is already there — not a data-loss guard. Pass
`--force` to overwrite:

```bash
owa-drive put ./report.md /Documents/report.md            # exits 15 if exists
owa-drive put ./report.md /Documents/report.md --force    # overwrites
```

Pass more than one local path and the trailing positional becomes the remote
*directory*; each local file is uploaded to `<remote-dir>/<basename>`:

```bash
owa-drive put ./*.md /Documents/notes
# {
#   "uploaded": [{"local": "...", "remote": "/Documents/notes/foo.md", "item": {...}}],
#   "skipped":  [{"local": "...", "remote": "/Documents/notes/bar.md"}],
#   "failed":   []
# }
```

In batch mode, existing remote files are *skipped* (not refused) so the rest
of the batch keeps going; per-file upload failures are recorded in `failed`
but never abort the run. Exit code is `0` when `failed` is empty (skips count
as success), `1` otherwise. `--force` re-uploads everything and skips the
existence preflight altogether.

## Output contract

JSON on stdout by default; diagnostics/prompts/errors on stderr. `--pretty` is
the human-readable opt-in. `get` streams raw file bytes to stdout (or a file
with `--out`). Exit codes follow the suite taxonomy (see
[security.md](security.md) and [agent-integration.md](agent-integration.md)).

## Machine / agent surface

Every owa binary exposes the same machine surface:

- `owa-drive schema [<command>]` — JSON command schema (one command if named)
- `owa-drive --help --json` — same schema via the help flag
- `--agent` — wrap JSON stdout in a stable `{"_owa": ..., "data": ...}` envelope (or `OWA_AGENT=1`)
- `--err-json` — structured JSON errors on stderr (or `OWA_ERR_JSON=1`)
- `--doctor [--json]` — this tool's health / redaction doctor payload

See [agent-integration.md](agent-integration.md) for the full contract.

## Caveats

- `rm` (alias `delete`) deliberately requires `--confirm` (or an interactive
  "yes") for safety. The drive root is unconditionally refused.
- This is a CRUD tool, not a sync client. There is no folder upload, no
  resume, no conflict resolution beyond what Graph surfaces (409).
