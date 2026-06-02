"""owa-teams - Microsoft Teams CLI for Microsoft 365 (teams, channels, chats, messages)."""

from owa_core.version import suite_version

__version__ = suite_version()

# Defined after __version__ so cli.py can safely `from . import __version__`.
from .cli import main  # noqa: E402

__all__ = ["main", "__version__"]
