"""owa-core: shared library for the owa-tools consumer CLIs.

Stdlib only at runtime. No third-party dependencies.

Public surface (frozen at start of Phase 1):
    owa_core.auth      - owa-piggy bridge, version pin, identity probe
    owa_core.http      - urllib wrapper, retries, nextLink, etag, typed errors
    owa_core.config    - atomic kv config files with allowlists
    owa_core.dates     - parse, iso_week, resolve_tz (zoneinfo-first)
    owa_core.format    - render, pretty_table, csv/tsv/ndjson
    owa_core.dispatch  - declarative subcommand specs, schema generation
    owa_core.errors    - exit-code taxonomy, structured-error envelope
    owa_core.tty       - is_interactive, confirm
    owa_core.jwt       - exp/scp parsing without signature validation

API additions require a CHANGELOG-core.md entry and tests in owa_core/tests/.
"""
__version__ = "0.0.0.dev0"
