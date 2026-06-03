"""Canonical registry of the owa-tools consumer binaries.

Single source of truth for "which consumer CLIs ship in this suite".
The umbrella `owa` binary (owa.cli.CONSUMERS) and the health probe
(owa_doctor.probe.SIBLINGS) both derive their tool lists from here so
the two can never drift - adding a tool in one place is impossible to
forget in the other.

`owa-piggy` is deliberately NOT listed: it is the separately released
auth broker, not a consumer CLI. Callers that also probe the broker
(owa-doctor) prepend it explicitly.

Stdlib only; no imports of consumer packages - this module holds plain
strings so depending on it introduces no coupling to tool code.
"""
from __future__ import annotations

# Order is the canonical display order used by `owa list`, `owa schema`,
# and `owa-doctor`. Keep new tools appended in install/announce order.
CONSUMER_TOOLS: tuple[str, ...] = (
    "owa-cal",
    "owa-mail",
    "owa-graph",
    "owa-doctor",
    "owa-people",
    "owa-sched",
    "owa-drive",
    "owa-todo",
    "owa-planner",
    "owa-sites",
    "owa-teams",
    "owa-vids",
)

__all__ = ["CONSUMER_TOOLS"]
