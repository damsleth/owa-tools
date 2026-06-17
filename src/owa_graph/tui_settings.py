"""Settings dataclass for the owa-graph interactive explorer (TUI).

Mirrors owa_mail/tui_settings.py and delegates the cycle/persist mechanics to
owa_core.tui_kit.settings, so every owa-* TUI persists view settings the same
way. The graph explorer adds:

- pretty_json / scope_warnings  — on/off toggles (cycle wraps two values)
- default_audience / default_path — free-text seed for the first fetch
- bookmarks — a JSON-encoded list of {audience,path,label}, one config string

Config key names (must match ALLOWED_KEYS in config.py):
  graph_tui_reading_pane, graph_tui_split_ratio, graph_tui_pretty_json,
  graph_tui_scope_warnings, graph_tui_default_audience, graph_tui_default_path,
  graph_tui_bookmarks.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Final

from owa_core.tui_kit import settings as _kit

# ---------------------------------------------------------------------------
# Allowed values (ordered tuples define cycle order)
# ---------------------------------------------------------------------------

READING_PANE_VALUES: Final[tuple[str, ...]] = ('right', 'bottom', 'off')
SPLIT_RATIO_VALUES: Final[tuple[int, ...]] = (40, 50, 60)
TOGGLE_VALUES: Final[tuple[str, ...]] = ('on', 'off')

_FREE_TEXT_FIELDS: Final[frozenset[str]] = frozenset(
    {'default_audience', 'default_path', 'bookmarks'}
)

_ALLOWED: Final[dict[str, tuple]] = {
    'reading_pane': READING_PANE_VALUES,
    'split_ratio': SPLIT_RATIO_VALUES,
    'pretty_json': TOGGLE_VALUES,
    'scope_warnings': TOGGLE_VALUES,
}

_FIELD_TO_KEY: Final[dict[str, str]] = {
    'reading_pane': 'graph_tui_reading_pane',
    'split_ratio': 'graph_tui_split_ratio',
    'pretty_json': 'graph_tui_pretty_json',
    'scope_warnings': 'graph_tui_scope_warnings',
    'default_audience': 'graph_tui_default_audience',
    'default_path': 'graph_tui_default_path',
    'bookmarks': 'graph_tui_bookmarks',
}
_KEY_TO_FIELD: Final[dict[str, str]] = {v: k for k, v in _FIELD_TO_KEY.items()}


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Settings:
    """Immutable TUI settings snapshot."""

    reading_pane: str = 'right'
    split_ratio: int = 50
    pretty_json: str = 'on'
    scope_warnings: str = 'on'
    default_audience: str = 'graph'
    default_path: str = ''
    bookmarks: str = '[]'


DEFAULTS = Settings()


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def cycle(settings: Settings, field: str) -> Settings:
    """Return a new Settings with *field* advanced to its next allowed value.

    Wraps around. Free-text fields (default_audience/default_path/bookmarks)
    cannot be cycled; cycle() returns the same Settings unchanged.
    """
    return _kit.cycle(settings, field, allowed=_ALLOWED, free_text=_FREE_TEXT_FIELDS)


def from_config(config: dict) -> Settings:
    """Build a Settings from a raw config dict. Unknown/invalid values fall
    back to the per-field default; *split_ratio* is coerced to int."""
    return _kit.from_config(
        config,
        defaults=DEFAULTS,
        field_to_key=_FIELD_TO_KEY,
        allowed=_ALLOWED,
        free_text=_FREE_TEXT_FIELDS,
        coercers={'split_ratio': int},
    )


def to_config_dict(settings: Settings) -> dict[str, str]:
    """Serialise a Settings to shell-safe string values keyed by config key."""
    return _kit.to_config_dict(settings, field_to_key=_FIELD_TO_KEY)


# ---------------------------------------------------------------------------
# Bookmarks (JSON-encoded list of {audience,path,label} in one config string)
# ---------------------------------------------------------------------------

def parse_bookmarks(raw: str) -> list[dict]:
    """Decode the bookmarks config string to a list of dicts. Tolerant: a
    malformed or non-list value yields an empty list."""
    try:
        data = json.loads(raw or '[]')
    except (ValueError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    return [b for b in data if isinstance(b, dict) and 'audience' in b and 'path' in b]


def dump_bookmarks(bookmarks: list[dict]) -> str:
    """Encode bookmarks to a compact config string, persisting only the
    (audience, path, label) triple — never response bodies."""
    trimmed = [
        {'audience': b['audience'], 'path': b['path'], 'label': b.get('label', '')}
        for b in bookmarks
        if isinstance(b, dict) and 'audience' in b and 'path' in b
    ]
    return json.dumps(trimmed, ensure_ascii=False, separators=(',', ':'))
