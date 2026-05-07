"""TTY detection and interactive confirm helper.

Public surface:
    is_interactive() -> bool
    confirm(prompt, *, force=False) -> bool

confirm refuses to prompt when stdin is not a TTY; raises UsageError
with a hint to pass --yes/--confirm. With force=True, returns True
without prompting.
"""
from __future__ import annotations

import sys

from .errors import UsageError


def is_interactive() -> bool:
    """True iff both stdin and stderr are TTYs.

    stderr matters because the prompt is written there; stdin matters
    because that's where the answer comes from.
    """
    try:
        return bool(sys.stdin.isatty() and sys.stderr.isatty())
    except (AttributeError, ValueError):
        return False


def confirm(prompt: str, *, force: bool = False) -> bool:
    """Prompt for y/N on stderr; refuse to prompt off-TTY.

    With force=True, returns True without writing anything. Off-TTY
    (no force), raises UsageError so the caller exits with code 2 and
    a clear hint to pass --yes/--confirm.
    """
    if force:
        return True
    if not is_interactive():
        raise UsageError(
            "refusing to prompt: stdin is not a TTY",
            hint="pass --yes or --confirm for non-interactive use",
        )
    sys.stderr.write(f"{prompt} [y/N]: ")
    sys.stderr.flush()
    answer = sys.stdin.readline().strip().lower()
    return answer in ("y", "yes")
