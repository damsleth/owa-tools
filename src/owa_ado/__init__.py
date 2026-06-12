"""owa-ado - Azure DevOps CLI for Outlook / Microsoft 365 identities.

Auth flows through the owa-piggy broker (`--audience devops`); a profile
that captured the Azure DevOps client's refresh token (see owa-piggy's
non-FOCI capture path) brokers tokens with `aud=499b84ac-...`, the Azure
DevOps resource. owa-ado never touches refresh tokens itself.
"""

from owa_core.version import suite_version

__version__ = suite_version()

from .cli import main  # noqa: E402

__all__ = ["main", "__version__"]
