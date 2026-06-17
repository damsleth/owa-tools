"""Generic view-settings engine for owa-* TUIs.

A tool defines its own frozen ``Settings`` dataclass plus three metadata
maps (field→config-key, field→allowed-values, the set of free-text fields)
and delegates ``cycle`` / ``from_config`` / ``to_config_dict`` here, so every
tool persists and cycles view settings identically without copying the logic.

The engine never imports a tool's dataclass; it reconstructs instances via
``type(defaults)(**kwargs)`` and mutates with :func:`dataclasses.replace`,
so any frozen dataclass works.
"""
from __future__ import annotations

from dataclasses import replace


def cycle(settings, field, *, allowed, free_text=frozenset()):
    """Return a new settings object with *field* advanced to its next value.

    Free-text fields are returned unchanged (same object). Unknown fields
    raise ``ValueError``. Wraps around at the end of the allowed sequence; an
    out-of-range current value advances to the first allowed value.
    """
    if field in free_text:
        return settings
    if field not in allowed:
        raise ValueError(f'unknown settings field: {field!r}')
    seq = list(allowed[field])
    current = getattr(settings, field)
    try:
        idx = seq.index(current)
    except ValueError:
        idx = -1
    return replace(settings, **{field: seq[(idx + 1) % len(seq)]})


def from_config(config, *, defaults, field_to_key, allowed,
                free_text=frozenset(), coercers=None):
    """Build a settings object from a config dict, falling back to *defaults*.

    Parameters
    ----------
    config        : the persisted ``{key: str}`` mapping.
    defaults      : a settings instance providing per-field defaults *and*
                    the concrete type to construct.
    field_to_key  : ``{field: config_key}``.
    allowed       : ``{field: sequence_of_allowed_values}`` for enum fields.
    free_text     : fields accepted as-is (stored as ``str``).
    coercers      : optional ``{field: callable(raw)->value}`` for non-str
                    fields (e.g. ``{'split_ratio': int}``). A coerced value
                    that is not in ``allowed[field]`` (when listed) falls back
                    to the default.
    """
    coercers = coercers or {}
    kwargs = {}
    for field, key in field_to_key.items():
        raw = config.get(key)
        default = getattr(defaults, field)
        if raw is None:
            kwargs[field] = default
        elif field in coercers:
            try:
                val = coercers[field](raw)
            except (ValueError, TypeError):
                val = default
            if field in allowed and val not in allowed[field]:
                val = default
            kwargs[field] = val
        elif field in free_text:
            kwargs[field] = str(raw)
        elif field in allowed:
            kwargs[field] = raw if raw in allowed[field] else default
        else:
            kwargs[field] = raw
    return type(defaults)(**kwargs)


def to_config_dict(settings, *, field_to_key):
    """Serialize the persisted settings fields to a ``{config_key: str}`` dict."""
    return {key: str(getattr(settings, field))
            for field, key in field_to_key.items()}
