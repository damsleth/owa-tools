"""Path-pattern → scope-requirement matcher for the v0.5 scope-hint
feature.

The manifest at ``data/scopes.json`` maps templated paths (e.g.
``/users/{id}/manager``) to the delegated scopes Graph requires for a
given verb. The matcher tokenizes both the manifest entry and the
caller's concrete path on ``/`` and treats ``{...}`` segments as
wildcards. Match precision is intentionally cheap - the hint is
advisory, never blocks the call.

Lazy-loaded: the manifest is read once on first use and cached. The
verb-first happy path (`owa-graph GET /me`) only pays the cost if the
hint isn't suppressed by ``OWA_GRAPH_NO_SCOPE_HINTS=1``.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional, Tuple


_DATA_PATH = Path(__file__).resolve().parent / 'data' / 'scopes.json'

# Cached manifest: list of (verb, segments, scopes) tuples after a
# one-shot transform. ``None`` means "not yet loaded"; ``[]`` means
# "load failed - operate in no-hint mode forever after".
_MANIFEST: Optional[List[Tuple[str, List[str], List[str]]]] = None


def _normalize(path: str) -> List[str]:
    """Tokenize a path on '/' and strip an optional leading slash. Query
    strings and fragments are dropped - the manifest only cares about
    the path part."""
    p = path.split('?', 1)[0].split('#', 1)[0]
    if p.startswith('/'):
        p = p[1:]
    return [seg for seg in p.split('/') if seg]


def _load_manifest():
    global _MANIFEST
    if _MANIFEST is not None:
        return _MANIFEST
    try:
        data = json.loads(_DATA_PATH.read_text())
        out: List[Tuple[str, List[str], List[str]]] = []
        for entry in data.get('scopes', []):
            verb = (entry.get('verb') or '').upper()
            path = entry.get('path') or ''
            scopes = entry.get('scopes') or []
            if not (verb and path and scopes):
                continue
            out.append((verb, _normalize(path), list(scopes)))
        _MANIFEST = out
    except Exception:
        _MANIFEST = []
    return _MANIFEST


def _segments_match(template: List[str], concrete: List[str]) -> bool:
    """`template` may contain `{...}` wildcards; concrete must be the
    same length and match segment-for-segment."""
    if len(template) != len(concrete):
        return False
    for t, c in zip(template, concrete):
        if t.startswith('{') and t.endswith('}'):
            continue
        if t != c:
            return False
    return True


def required_scopes(verb: str, path: str) -> List[str]:
    """Return the list of delegated scopes the manifest declares for
    the (verb, path) tuple, or [] if no entry matches.

    Picks the first match in manifest order. Manifest entries are
    written most-specific-first so a literal path beats a templated
    one when both apply.
    """
    verb = (verb or '').upper()
    segs = _normalize(path)
    for entry_verb, entry_segs, entry_scopes in _load_manifest():
        if entry_verb != verb:
            continue
        if _segments_match(entry_segs, segs):
            return list(entry_scopes)
    return []


def reset_cache_for_tests():
    """Test-only: drop the cached manifest so a freshly-patched data
    file is picked up. Production code never calls this."""
    global _MANIFEST
    _MANIFEST = None
