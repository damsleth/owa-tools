import io

import pytest

from owa_core import tty
from owa_core.errors import UsageError


class _TTY(io.StringIO):
    def isatty(self):
        return True


class _NotTTY(io.StringIO):
    def isatty(self):
        return False


def test_require_confirm_or_tty_allows_confirm_without_tty():
    assert tty.require_confirm_or_tty(confirm=True, stdin=_NotTTY(), stderr=_NotTTY()) is True


def test_require_confirm_or_tty_rejects_non_interactive():
    with pytest.raises(UsageError):
        tty.require_confirm_or_tty(action='delete', stdin=_NotTTY(), stderr=_TTY())


def test_confirm_accepts_yes_response():
    stderr = _TTY()
    assert tty.confirm('Delete? ', stdin=_TTY('yes\n'), stderr=stderr) is True
    assert stderr.getvalue() == 'Delete? '


def test_confirm_rejects_unaccepted_response():
    assert tty.confirm('type yes: ', accepted=('yes',), stdin=_TTY('y\n'), stderr=_TTY()) is False
