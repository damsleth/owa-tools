# AGENTS.md

`owa_people` handles Graph people, contacts, and directory lookups.

- Auth audience is `graph`.
- This package is the first migrated consumer of shared `owa_core.auth`,
  `owa_core.errors`, and `owa_core.http`; keep new work on those paths.
- Normalizers must tolerate sparse Graph responses without traceback.
- No command stores people data locally.
- Docs live in `docs/people.md`.

Nearest tests: `src/tests/people/`, `src/tests/core/`.

Verify:

```bash
.venv/bin/ruff check src/owa_people src/tests/people
.venv/bin/python -m pytest -q src/tests/people tests/core
```
