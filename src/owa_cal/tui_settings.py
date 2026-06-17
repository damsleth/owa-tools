"""Settings dataclass for the owa-cal TUI.

Provides:
- Settings dataclass with defaults and ordered allowed-value tuples per
  enum field.
- cycle(settings, field) -> Settings  (wraps to next allowed value)
- from_config(config) -> Settings     (validates; unknown/invalid -> default)
- to_config_dict(settings) -> dict[str, str]  (shell-safe KEY/VALUE pairs)

Config key names (must match ALLOWED_KEYS in config.py):
  tui_reading_pane, tui_split_ratio, tui_day_range, tui_show_declined.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from owa_core.tui_kit import settings as _kit

# ---------------------------------------------------------------------------
# Allowed values (ordered tuples define cycle order)
# ---------------------------------------------------------------------------

READING_PANE_VALUES: Final[tuple[str, ...]] = ('right', 'bottom', 'off')
SPLIT_RATIO_VALUES: Final[tuple[int, ...]] = (40, 50, 60)
DAY_RANGE_VALUES: Final[tuple[str, ...]] = ('today', 'week', 'month')
SHOW_DECLINED_VALUES: Final[tuple[str, ...]] = ('yes', 'no')
EVENT_DETAIL_VALUES: Final[tuple[str, ...]] = ('full', 'basic')

# Mapping of field -> allowed-values tuple (for enum fields only)
_ALLOWED: Final[dict[str, tuple]] = {
    'reading_pane': READING_PANE_VALUES,
    'split_ratio': SPLIT_RATIO_VALUES,
    'day_range': DAY_RANGE_VALUES,
    'show_declined': SHOW_DECLINED_VALUES,
    'event_detail': EVENT_DETAIL_VALUES,
}

# Free-text fields (none for cal, but keep the frozenset shape)
_FREE_TEXT_FIELDS: Final[frozenset[str]] = frozenset()

# Config key <-> field name mapping
_FIELD_TO_KEY: Final[dict[str, str]] = {
    'reading_pane': 'tui_reading_pane',
    'split_ratio': 'tui_split_ratio',
    'day_range': 'tui_day_range',
    'show_declined': 'tui_show_declined',
    'event_detail': 'tui_event_detail',
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
    day_range: str = 'today'
    show_declined: str = 'no'
    event_detail: str = 'full'


# ---------------------------------------------------------------------------
# Default instance (singleton convenience)
# ---------------------------------------------------------------------------

DEFAULTS = Settings()


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def cycle(settings: Settings, field: str) -> Settings:
    """Return a new Settings with *field* advanced to its next allowed value.

    Wraps around.
    """
    return _kit.cycle(settings, field, allowed=_ALLOWED, free_text=_FREE_TEXT_FIELDS)


def from_config(config: dict) -> Settings:
    """Build a Settings from a raw config dict (as returned by load_config).

    Unknown or invalid values fall back to the per-field default.
    *split_ratio* is stored as a string; we coerce to int here.
    """
    return _kit.from_config(
        config,
        defaults=DEFAULTS,
        field_to_key=_FIELD_TO_KEY,
        allowed=_ALLOWED,
        free_text=_FREE_TEXT_FIELDS,
        coercers={'split_ratio': int},
    )


def to_config_dict(settings: Settings) -> dict[str, str]:
    """Serialise a Settings to a dict of shell-safe string values.

    All values are stored as strings. The dict keys match ALLOWED_KEYS in
    config.py.
    """
    return _kit.to_config_dict(settings, field_to_key=_FIELD_TO_KEY)
