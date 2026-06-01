"""Settings dataclass for the owa-mail TUI.

Provides:
- Settings dataclass with defaults and ordered allowed-value tuples per
  enum field.
- cycle(settings, field) -> Settings  (wraps to next allowed value)
- from_config(config) -> Settings     (validates; unknown/invalid -> default)
- to_config_dict(settings) -> dict[str, str]  (shell-safe KEY/VALUE pairs)

Config key names (must match ALLOWED_KEYS in config.py):
  tui_reading_pane, tui_split_ratio, tui_sort_by, tui_date_format,
  tui_date_custom.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Final

# ---------------------------------------------------------------------------
# Allowed values (ordered tuples define cycle order)
# ---------------------------------------------------------------------------

READING_PANE_VALUES: Final[tuple[str, ...]] = ('right', 'bottom', 'off')
SPLIT_RATIO_VALUES: Final[tuple[int, ...]] = (40, 50, 60)
SORT_BY_VALUES: Final[tuple[str, ...]] = (
    'date_desc',
    'date_asc',
    'sender',
    'subject',
    'unread_first',
)
DATE_FORMAT_VALUES: Final[tuple[str, ...]] = (
    'iso8601',
    'ddmm',
    'ddmm_hhmm',
    'custom',
)

# Fields that are free-text (not cycled through an enum)
_FREE_TEXT_FIELDS: Final[frozenset[str]] = frozenset({'date_custom'})

# Mapping of field -> allowed-values tuple (for enum fields only)
_ALLOWED: Final[dict[str, tuple]] = {
    'reading_pane': READING_PANE_VALUES,
    'split_ratio': SPLIT_RATIO_VALUES,
    'sort_by': SORT_BY_VALUES,
    'date_format': DATE_FORMAT_VALUES,
}

# Config key <-> field name mapping
_FIELD_TO_KEY: Final[dict[str, str]] = {
    'reading_pane': 'tui_reading_pane',
    'split_ratio': 'tui_split_ratio',
    'sort_by': 'tui_sort_by',
    'date_format': 'tui_date_format',
    'date_custom': 'tui_date_custom',
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
    sort_by: str = 'date_desc'
    date_format: str = 'iso8601'
    date_custom: str = ''


# ---------------------------------------------------------------------------
# Default instance (singleton convenience)
# ---------------------------------------------------------------------------

DEFAULTS = Settings()


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def cycle(settings: Settings, field: str) -> Settings:
    """Return a new Settings with *field* advanced to its next allowed value.

    Wraps around. *date_custom* is free-text and cannot be cycled; calling
    cycle() on it returns the same Settings unchanged.
    """
    if field in _FREE_TEXT_FIELDS:
        return settings
    if field not in _ALLOWED:
        raise ValueError(f'unknown settings field: {field!r}')
    allowed = _ALLOWED[field]
    current = getattr(settings, field)
    try:
        idx = list(allowed).index(current)
    except ValueError:
        idx = -1  # invalid current value; jump to first
    next_val = allowed[(idx + 1) % len(allowed)]
    return replace(settings, **{field: next_val})


def from_config(config: dict) -> Settings:
    """Build a Settings from a raw config dict (as returned by load_config).

    Unknown or invalid values fall back to the per-field default.
    *split_ratio* is stored as a string; we coerce to int here.
    """
    kwargs: dict = {}

    for field, key in _FIELD_TO_KEY.items():
        raw = config.get(key)
        default = getattr(DEFAULTS, field)

        if raw is None:
            # Key absent in config — use default
            kwargs[field] = default
            continue

        if field == 'split_ratio':
            try:
                val = int(raw)
            except (ValueError, TypeError):
                val = default
            if val not in SPLIT_RATIO_VALUES:
                val = default
            kwargs[field] = val

        elif field in _FREE_TEXT_FIELDS:
            # Accept any string
            kwargs[field] = str(raw)

        else:
            # Enum field: validate against allowed tuple
            allowed = _ALLOWED[field]
            if raw in allowed:
                kwargs[field] = raw
            else:
                kwargs[field] = default

    return Settings(**kwargs)


def to_config_dict(settings: Settings) -> dict[str, str]:
    """Serialise a Settings to a dict of shell-safe string values.

    All values are stored as strings. The dict keys match ALLOWED_KEYS in
    config.py.
    """
    return {
        _FIELD_TO_KEY['reading_pane']: settings.reading_pane,
        _FIELD_TO_KEY['split_ratio']: str(settings.split_ratio),
        _FIELD_TO_KEY['sort_by']: settings.sort_by,
        _FIELD_TO_KEY['date_format']: settings.date_format,
        _FIELD_TO_KEY['date_custom']: settings.date_custom,
    }
