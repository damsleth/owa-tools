"""TTY helpers for destructive CLI confirmations."""
import sys

from .errors import UsageError


def is_interactive(stdin=None, stderr=None):
    stdin = stdin or sys.stdin
    stderr = stderr or sys.stderr
    return bool(stdin.isatty() and stderr.isatty())


def require_confirm_or_tty(*, confirm=False, yes=False, action='operation', stdin=None, stderr=None):
    if confirm or yes:
        return True
    if not is_interactive(stdin=stdin, stderr=stderr):
        raise UsageError(f'{action} refuses to run non-interactively without --confirm')
    return False


def confirm(prompt, *, confirm=False, yes=False, accepted=None, stdin=None, stderr=None):
    stdin = stdin or sys.stdin
    stderr = stderr or sys.stderr
    if require_confirm_or_tty(confirm=confirm, yes=yes, stdin=stdin, stderr=stderr):
        return True
    accepted = set(accepted or ('y', 'yes'))
    stderr.write(prompt)
    stderr.flush()
    answer = stdin.readline().strip().lower()
    return answer in accepted
