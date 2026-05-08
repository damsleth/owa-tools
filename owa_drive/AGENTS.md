# AGENTS.md

`owa_drive` handles OneDrive metadata and small-file content transfers.

- Auth audience is `graph`.
- Binary stdout must stay exact bytes for download/content paths.
- JSON wrapping is not allowed for binary stdout unless output goes to `--out`.
- Delete, overwrite, move, and upload behavior require explicit confirmation
  and conflict tests before release.
- Root deletion and path traversal must be rejected.
- Docs live in `docs/drive.md` if present; otherwise update docs before release.

Nearest tests: `tests/drive/`.

Verify:

```bash
.venv/bin/ruff check owa_drive tests/drive
.venv/bin/python -m pytest -q tests/drive
```
