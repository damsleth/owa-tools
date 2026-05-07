"""Tiny argv-parsing helpers shared across resource modules.

Each handler is 5-15 LOC; the shared bits live here so we don't repeat
the same flag loop 100 times.

Convention: every flag takes ``--name value`` (no ``=`` form, no short
flags, no clustering). Boolean flags (``--unread``) are presence-only.
Positional args are returned in order.
"""
from __future__ import annotations

from typing import List, Optional, Tuple


def parse(args: List[str], *, flags: Tuple[str, ...] = (),
          bools: Tuple[str, ...] = ()) -> Tuple[dict, List[str]]:
    """Walk ``args`` and split into (parsed-dict, positionals).

    - Each name in ``flags`` consumes one value.
    - Each name in ``bools`` toggles to ``True``.
    - Anything else is positional.
    - Unknown ``--xxx`` tokens raise ``ValueError`` so the caller can
      surface a clean error.
    """
    parsed: dict = {}
    positional: List[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        if a in flags:
            if i + 1 >= len(args):
                raise ValueError(f'{a} requires a value')
            parsed[a] = args[i + 1]
            i += 2
            continue
        if a in bools:
            parsed[a] = True
            i += 1
            continue
        if a.startswith('--'):
            raise ValueError(f'unknown flag: {a}')
        positional.append(a)
        i += 1
    return parsed, positional


def opt(parsed: dict, name: str, default: Optional[str] = None) -> Optional[str]:
    """Return ``parsed[name]`` if set, else ``default``."""
    return parsed.get(name, default)
