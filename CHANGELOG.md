# Changelog

Per-tool changelog. Per-tool versions advance independently; the
monorepo itself has no separate version.

Format: append a `### vX.Y.Z` section under the relevant tool when
tagging a release.

## owa-cal

## owa-mail

## owa-graph

## owa-doctor

## owa-people

## owa-sched

## owa-drive

## owa (umbrella)

Thin discovery binary. Subcommands:

- `owa list` - JSON list of installed consumers and their versions.
- `owa schema [--tool <name>]` - aggregate `<tool> schema` output.
- `owa doctor [...]` - forwards to `owa-doctor probe`.
- `owa version` - umbrella version.

Real work lives in the per-tool binaries.
