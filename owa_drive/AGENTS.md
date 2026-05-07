# AGENTS.md

Instructions for AI coding agents working in this repo.

## What this is

`owa-drive` is a stdlib-only Python CLI for OneDrive CRUD against
Outlook / Microsoft 365. JSON metadata on stdout, file content on
stdout for `get` (raw bytes), logs on stderr, `--pretty` for humans.

Sibling of `owa-cal`/`owa-mail`/`owa-people`/`owa-sched`. Backend
is **Microsoft Graph** `/me/drive`. The OWA SPA scopes carry
`Files.ReadWrite.All`, which covers the read+write subset this
tool exposes.

## Ground rules

- **Stdlib only** at runtime. No deps. `pytest` is dev-only.
- **JSON metadata on stdout, file content on stdout for `get`.**
  Don't conflate them. `get` writes raw bytes; everything else
  writes JSON or `--pretty` text.
- **Never commit real OneDrive paths or item IDs in tests.**
  Use obvious fakes (`/Documents/foo.txt`).
- **Audience is `graph`.**
- **Path addressing only.** `paths.item_endpoint` is the one place
  where Graph URL shapes are constructed. Don't sprinkle
  `/me/drive/items/...` throughout `cli.py` - if you need by-id
  addressing, add it as a sibling helper in `paths.py` and pin it
  in `tests/test_paths.py`.
- **Refuse to delete the drive root.** `delete_endpoint('')`
  raises; `cmd_rm` short-circuits on it. Don't paper over this.
- **Upload limit is 4 MB.** Larger files need a Graph upload
  session, which is a future expansion. Don't pretend `put` works
  for large files.

## Layout

```
owa_drive/
  __init__.py     # re-exports `main`
  __main__.py     # `python -m owa_drive`
  cli.py          # arg parsing + dispatch + cmd_* handlers
  auth.py         # owa-piggy bridge, audience=graph
  api.py          # Graph HTTP helpers (JSON + binary GET/PUT)
  config.py       # CONFIG_PATH, load/save, profile alias only
  paths.py        # path -> Graph endpoint translation (pure)
  items.py        # normalize_item (driveItem -> flat shape, pure)
  format.py       # --pretty rendering for items
  jwt.py          # token_minutes_remaining (no signature validation)
tests/            # pytest suite, no network
pyproject.toml
```

## Working on this repo

- Each new subcommand is a `cmd_*` function in `cli.py` with its
  own flag loop. Match the existing style.
- All new endpoint shapes go through `paths.py` and get a test in
  `test_paths.py`. The endpoint format (colons, percent-encoding)
  is a contract; tests pin it.
- Binary content paths (`get`/`put`) go through
  `api.api_get_binary` / `api.api_put_binary`. Never JSON-encode
  upload bodies.

## Verification before claiming done

- `python -m compileall -q owa_drive` passes.
- `python -m owa_drive --help` runs without traceback on a clean
  machine.
- `pytest -q` is green.
- If you touched the file path: `owa-drive ls --pretty`,
  `owa-drive get <path> --out /tmp/X`, and a round-trip
  `put` + `rm`. If you cannot run against a real profile, say so
  explicitly.

## What NOT to do

- Don't remove the `--confirm` requirement on `rm`. It's there to
  catch agent mistakes; the user can override per-call.
- Don't add upload-session support speculatively without testing
  it - chunked upload protocol has its own pitfalls (range math,
  resume on failure).
- Don't switch the audience to Outlook - Outlook REST does not
  expose drives.
