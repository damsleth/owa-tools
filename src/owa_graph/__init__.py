"""owa-graph - Microsoft Graph CLI for one-off queries."""

from owa_core.version import suite_version

__version__ = suite_version()

# Defined after __version__ so cli.py can safely `from . import __version__`.
from .cli import main  # noqa: E402

__all__ = ["main", "__version__"]
