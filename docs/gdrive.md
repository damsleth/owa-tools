# owa-gdrive

Read-only Google Drive CLI: list and search files, show metadata, download
files, and export Google Docs/Sheets/Slides/Drawings. It never uploads,
moves, renames or deletes anything. (For OneDrive, use `owa-drive`.)

## Auth

Drive is read through an owa-piggy Google profile: a Google OAuth Desktop
client consented for `drive.readonly`, the same profile `owa-gmail` uses. No
API key is involved.

```bash
owa-piggy setup --profile brkh-g --google \
  --google-client-id <id>.apps.googleusercontent.com --google-client-secret <secret>
```

With exactly one Google profile, `owa-gdrive` picks it; otherwise pass
`--profile <alias>` or pin one with `owa-gdrive config --profile <alias>`.
`-A` fans out across Google profiles only; a Microsoft profile exits `2`.

## Commands

```bash
owa-gdrive ls --pretty
owa-gdrive ls 1hkXj6luvyJrFI2Pr6VhHdtzpxcm4SKpg --type file
owa-gdrive ls --name budget --pretty
owa-gdrive ls --search "styremøte" --all
owa-gdrive ls --shared
owa-gdrive ls --query "mimeType = 'application/pdf' and trashed = false"
owa-gdrive show 1aoGx5JoUltJ5MPrrcFhfHOUEneNeDaViEazcQbLEOQY --pretty
owa-gdrive get 1aoGx5JoUltJ5MPrrcFhfHOUEneNeDaViEazcQbLEOQY --out agenda.txt
owa-gdrive get 1aoGx5JoUltJ5MPrrcFhfHOUEneNeDaViEazcQbLEOQY --export-mime application/pdf --out agenda.pdf
owa-gdrive refresh
owa-gdrive config --profile brkh-g
```

- `owa-gdrive ls [folder-id]` lists a folder, folders first, by name. With no
  folder and no `--name`/`--search`/`--shared`/`--query` it lists My Drive's
  top level. `--name` and `--search` (full text) cover the whole Drive unless
  a folder id is given. `--type file|folder` filters; `--query` passes a raw
  Drive query and replaces the other filters. Trashed files are left out.
  `--max-results` is the page size (default 100, max 1000); when more exist
  the JSON is `{"files": [...], "next_page_token": "..."}`. `--all` follows
  every page.
- `owa-gdrive show <id>` prints `id, name, kind, mime_type, is_google_native,
  size, modified, created, parents, owners, web_view_link, trashed`.
- `owa-gdrive get <id>` downloads the file's bytes. Google-native files have
  no bytes of their own and are exported: Docs and Slides as `text/plain`,
  Sheets as `text/csv`, Drawings as `image/png`; `--export-mime` picks
  another format (e.g. `application/pdf`, or an Office type). Output goes to
  stdout unless `--out <file>`, which refuses to overwrite (exit `15`)
  without `--force`. `get` on a folder, Form or Site exits `2`. It cannot
  fan out across profiles.

Drive has no paths: files are addressed by id (from `ls`/`show`). Shared
drives are not included.

## Errors

The suite exit codes apply: `11` auth expired (re-run owa-piggy setup for the
Google profile), `13` unknown file id, `14` rate limited. Google sometimes
reports quota exhaustion as a `403`, which surfaces as `12`. Exports larger
than Google's 10 MB export limit fail with Drive's error.
