#!/usr/bin/env python3
"""Vendor a path manifest from Graph's CSDL metadata.

Fetches https://graph.microsoft.com/v1.0/$metadata and /beta/$metadata,
walks each schema's EntityContainer, and emits a sorted list of paths
suitable for tab completion.

Output shape (gzipped at owa_graph/data/paths.json.gz):

    {
      "$schema_version": 1,
      "v1.0": ["/me", "/me/messages", "/me/messages/{id}", ...],
      "beta": [...]
    }

Paths included:
  - root EntitySets (/users) and Singletons (/me)
  - key-keyed entity slot (/users/{id})
  - navigation properties up to NAV_DEPTH hops, with cycle detection
    (a NavigationProperty path that revisits an EntityType already on
    the current chain is dropped; otherwise user.manager.manager...
    expands forever).

Skipped (deliberately, for the v0.5 first cut):
  - Bound functions and actions. They double the path count and need
    separate parameter rendering. Cheaper to pull in later.
  - $count, $value, $ref, /microsoft.graph.<derivedType> casts -
    completion-irrelevant noise.
  - Action imports / function imports at the container level.

Run:
    python3 scripts/refresh-paths.py             # fetch live, write file
    python3 scripts/refresh-paths.py --dry       # print path count to stderr,
                                                 # don't write
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

NS = {
    'edmx': 'http://docs.oasis-open.org/odata/ns/edmx',
    'edm': 'http://docs.oasis-open.org/odata/ns/edm',
}

NAV_DEPTH = 2  # 0 = root only, 1 = /users/{id}/manager, 2 = .../manager/manager

PRIMITIVE_PREFIXES = ('Edm.',)
COLLECTION_PREFIX = 'Collection('

ENDPOINTS = [
    ('v1.0', 'https://graph.microsoft.com/v1.0/$metadata'),
    ('beta', 'https://graph.microsoft.com/beta/$metadata'),
]


def _tag(name):
    return f'{{{NS["edm"]}}}{name}'


def _fetch(url):
    req = urllib.request.Request(url, headers={'Accept': 'application/xml'})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def _strip_collection(t):
    if t.startswith(COLLECTION_PREFIX) and t.endswith(')'):
        return t[len(COLLECTION_PREFIX):-1], True
    return t, False


def _build_type_index(root):
    """Map fully-qualified EntityType name -> ET element. Resolves
    `Alias` attributes on Schema so `graph.user` and `microsoft.graph.user`
    point at the same node."""
    index = {}
    aliases = {}
    for schema in root.findall('.//' + _tag('Schema')):
        ns = schema.get('Namespace')
        alias = schema.get('Alias')
        if alias and ns:
            aliases[alias] = ns
        for et in schema.findall(_tag('EntityType')):
            full = f'{ns}.{et.get("Name")}'
            index[full] = et
    return index, aliases


def _resolve_type(name, type_index, aliases):
    """Look up an EntityType node by name, honoring Schema aliases."""
    if name in type_index:
        return type_index[name]
    head, _, tail = name.partition('.')
    if head in aliases:
        return type_index.get(f'{aliases[head]}.{tail}')
    return None


def _entity_chain(et, type_index, aliases):
    """Walk up BaseType to collect this entity type's full inheritance
    chain, root first. NavigationProperties from base types are visible
    on derived types in OData."""
    chain = [et]
    base = et.get('BaseType')
    seen = {et.get('Name')}
    while base:
        node = _resolve_type(base, type_index, aliases)
        if node is None or node.get('Name') in seen:
            break
        seen.add(node.get('Name'))
        chain.append(node)
        base = node.get('BaseType')
    return list(reversed(chain))  # root-most first


def _nav_props(et, type_index, aliases):
    """Collect (name, target_type, is_collection) for every
    NavigationProperty on this entity type (including inherited)."""
    out = []
    for ancestor in _entity_chain(et, type_index, aliases):
        for nav in ancestor.findall(_tag('NavigationProperty')):
            name = nav.get('Name')
            ttype = nav.get('Type') or ''
            inner, is_collection = _strip_collection(ttype)
            if inner.startswith(PRIMITIVE_PREFIXES):
                continue
            out.append((name, inner, is_collection))
    return out


def _has_key(et, type_index, aliases):
    """Does this entity type carry a Key declaration somewhere in its
    inheritance chain?"""
    for ancestor in _entity_chain(et, type_index, aliases):
        if ancestor.find(_tag('Key')) is not None:
            return True
    return False


def _expand(prefix, type_name, type_index, aliases, depth, visited, out):
    """Emit `prefix` and any navigation expansions reachable from
    `type_name`. `visited` is the set of EntityType full names already
    on this chain - prevents user.manager.manager.manager... cycles."""
    out.add(prefix)
    if depth <= 0:
        return
    et = _resolve_type(type_name, type_index, aliases)
    if et is None:
        return
    if type_name in visited:
        return
    next_visited = visited | {type_name}

    for nav_name, target_type, is_collection in _nav_props(
        et, type_index, aliases
    ):
        nav_path = f'{prefix}/{nav_name}'
        out.add(nav_path)
        target_et = _resolve_type(target_type, type_index, aliases)
        if target_et is None:
            continue
        if is_collection:
            if _has_key(target_et, type_index, aliases):
                # Single-item slot under the collection: /users/{id}/messages/{id}
                key_path = f'{nav_path}/{{id}}'
                _expand(
                    key_path, target_type, type_index, aliases,
                    depth - 1, next_visited, out,
                )
            else:
                _expand(
                    nav_path, target_type, type_index, aliases,
                    depth - 1, next_visited, out,
                )
        else:
            _expand(
                nav_path, target_type, type_index, aliases,
                depth - 1, next_visited, out,
            )


def _walk_container(root, type_index, aliases):
    """Drive expansion from each EntityContainer's EntitySet/Singleton
    members. Returns a sorted list of paths."""
    out = set()
    for container in root.findall('.//' + _tag('EntityContainer')):
        for es in container.findall(_tag('EntitySet')):
            name = es.get('Name')
            tname = es.get('EntityType') or ''
            base = f'/{name}'
            out.add(base)
            target_et = _resolve_type(tname, type_index, aliases)
            if target_et is None:
                continue
            if _has_key(target_et, type_index, aliases):
                key = f'{base}/{{id}}'
                _expand(key, tname, type_index, aliases, NAV_DEPTH, set(), out)
            else:
                _expand(base, tname, type_index, aliases, NAV_DEPTH, set(), out)
        for sg in container.findall(_tag('Singleton')):
            name = sg.get('Name')
            tname = sg.get('Type') or ''
            base = f'/{name}'
            _expand(base, tname, type_index, aliases, NAV_DEPTH, set(), out)
    return sorted(out)


def _build_endpoint(label, url):
    print(f'fetching {label} CSDL from {url}', file=sys.stderr)
    blob = _fetch(url)
    root = ET.fromstring(blob)
    type_index, aliases = _build_type_index(root)
    paths = _walk_container(root, type_index, aliases)
    print(f'  {label}: {len(paths)} paths', file=sys.stderr)
    return paths


def main():
    parser = argparse.ArgumentParser(
        description=(__doc__ or '').split('\n', 1)[0],
    )
    parser.add_argument(
        '--dry', action='store_true',
        help="don't write the manifest, just print the count",
    )
    parser.add_argument(
        '--output', default=None,
        help='override the output file (default: owa_graph/data/paths.json.gz)',
    )
    args = parser.parse_args()

    payload = {'$schema_version': 1}
    for label, url in ENDPOINTS:
        try:
            payload[label] = _build_endpoint(label, url)
        except Exception as e:
            print(f'  {label}: FAILED ({e})', file=sys.stderr)
            payload[label] = []

    if args.dry:
        return 0

    out_path = Path(args.output) if args.output else (
        Path(__file__).resolve().parent.parent
        / 'owa_graph' / 'data' / 'paths.json.gz'
    )
    raw = json.dumps(payload, separators=(',', ':')).encode()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(out_path, 'wb', compresslevel=9) as f:
        f.write(raw)
    print(
        f'wrote {out_path} ({out_path.stat().st_size} bytes, '
        f'{len(raw)} bytes uncompressed)',
        file=sys.stderr,
    )
    return 0


if __name__ == '__main__':
    sys.exit(main())
