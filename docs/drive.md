# owa-drive

Pipe-friendly OneDrive CRUD CLI for Outlook / Microsoft 365.
Sibling of `owa-cal` / `owa-mail` / `owa-people` / `owa-sched`.

JSON metadata on stdout, file content on stdout for `get`,
`--pretty` for humans. Auth is delegated to
[`owa-piggy`](https://github.com/damsleth/owa-piggy).

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

```bash
pipx install owa-drive    # once published
# or, from a clone:
pipx install .
```

Then ensure `owa-piggy` is set up:

```bash
brew install damsleth/tap/owa-piggy
owa-piggy setup --profile work --email you@example.com
```

## Commands

```bash
owa-drive ls [path] [--pretty]            # list folder (default: drive root)
owa-drive show <path> [--pretty]          # metadata for one item
owa-drive get <path> [--out local-path]   # download (stdout or file)
owa-drive put <local> <remote-path>       # upload (use - for stdin)
owa-drive rm <path> [--confirm]           # delete (interactive without --confirm)

owa-drive refresh
owa-drive config --profile crayon
```

## Caveats

- Upload limit is 4 MB. Larger files need a Graph upload session,
  which this tool does not implement yet.
- `rm` deliberately requires `--confirm` (or interactive "yes")
  for safety. The drive root is unconditionally refused.
- This is a CRUD tool, not a sync client. There is no folder
  upload, no resume, no conflict resolution beyond what Graph
  surfaces (409).

## License

MIT
