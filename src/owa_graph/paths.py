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


def next_segments(word: str, endpoint: str = 'v1.0') -> List[str]:
    """Next-tier completion candidates for the path fragment `word`.

    Given what the user has typed so far ('/me', '/me/', '/me/set'), return
    the full paths exactly one segment deeper, deduped. Parents (candidates
    that themselves have children) get a trailing '/' so the shell can offer
    another tab. This keeps each tab-press to one tier (~tens of entries)
    instead of dumping the whole ~3.5k-path tree.

    Rules:
      - '/me'      -> descends into /me (it's a complete node) -> /me/calendar, ...
      - '/me/'     -> same (trailing slash means "show children")
      - '/me/set'  -> siblings under /me, shell filters down to /me/settings
      - ''         -> top-level paths
    """
    paths = all_paths(endpoint)
    pset = set(paths)
    w = word or '/'
    # Descend when the word names a complete node or ends in '/'; otherwise the
    # last segment is partial, so complete siblings under its parent dir.
    descend = w.endswith('/') or (w.rstrip('/') in pset and w != '/')
    base = w.rstrip('/') if descend else w.rsplit('/', 1)[0]
    prefix = base + '/' if base else '/'
    out: dict = {}
    for p in paths:
        if not p.startswith(prefix):
            continue
        rest = p[len(prefix):]
        if not rest:
            continue
        seg = rest.split('/', 1)[0]
        cand = prefix + seg
        out[cand] = out.get(cand, False) or ('/' in rest)
    return [c + '/' if is_parent else c for c, is_parent in sorted(out.items())]


def dump_next(word: str, endpoint: str = 'v1.0', stream=None) -> int:
    """Print next-tier candidates one per line for the completion scripts."""
    out = stream or sys.stdout
    written = 0
    try:
        for c in next_segments(word, endpoint):
            out.write(c)
            out.write('\n')
            written += 1
    except BrokenPipeError:
        pass
    return written


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
