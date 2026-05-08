# AGENTS.md

`owa_graph` is the raw Microsoft Graph client plus curated resource shortcuts.

- Raw verb-first mode and resource shortcuts are both public command surfaces.
- Auth audience defaults to `graph`, but explicit audience flags are part of the
  release contract.
- Pagination, NDJSON, resource path builders, and scope hints are high-risk and
  need focused tests.
- `--curl` and `--az` helpers must not leak tokens by default before release.
- Docs live in `docs/graph.md`.

Nearest tests: `tests/graph/`.

Verify:

```bash
.venv/bin/ruff check owa_graph tests/graph
.venv/bin/python -m pytest -q tests/graph
```
