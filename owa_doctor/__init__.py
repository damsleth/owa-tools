"""owa-doctor - health-check meta-CLI for the owa-* suite."""

from owa_core.version import suite_version

__version__ = suite_version()

from .cli import main  # noqa: E402

__all__ = ["main", "__version__"]
