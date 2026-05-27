"""Lazy reader for the vendored Graph path manifest.

`owa_graph/data/paths.json.gz` ships ~10k OData paths extracted from
Graph's CSDL metadata; it is a committed artifact regenerated when the
schema gains new paths. The completion scripts call `dump_paths()` once
per tab-press to render the candidate list; we keep the gzip read out of
the import path so the verb-first happy case stays fast.
"""
from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path
from typing import List, Optional

_DATA_PATH = Path(__file__).resolve().parent / 'data' / 'paths.json.gz'

_CACHE: Optional[dict] = None


def _load() -> dict:
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    try:
        with gzip.open(_DATA_PATH, 'rb') as f:
            _CACHE = json.loads(f.read().decode())
    except Exception:
        _CACHE = {}
    return _CACHE


def reset_cache_for_tests():
    global _CACHE
    _CACHE = None


def known_endpoints() -> List[str]:
    """Return the schema labels present in the manifest (typically
    ['v1.0', 'beta'])."""
    data = _load()
    return [k for k in data.keys() if not k.startswith('$')]


def all_paths(endpoint: str = 'v1.0') -> List[str]:
    """All paths for the given endpoint, or [] if missing/load failed."""
    data = _load()
    paths = data.get(endpoint)
    return list(paths) if isinstance(paths, list) else []


def dump_paths(endpoint: str = 'v1.0', stream=None) -> int:
    """Print every path on its own line. Used by the completion
    scripts via `owa-graph __complete paths`. Returns the number of
    lines written. Tolerates a closed pipe (common when piped into
    `head` or `compgen` truncates) without raising."""
    out = stream or sys.stdout
    paths = all_paths(endpoint)
    written = 0
    try:
        for p in paths:
            out.write(p)
            out.write('\n')
            written += 1
    except BrokenPipeError:
        pass
    return written


if __name__ == '__main__':
    # Allow `python -m owa_graph.paths [v1.0|beta]` so the completion
    # scripts can shell out to it without writing Python themselves.
    ep = sys.argv[1] if len(sys.argv) > 1 else 'v1.0'
    dump_paths(ep)
