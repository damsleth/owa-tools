"""cal-cli - calendar CLI for Outlook / Microsoft 365.

Pipe-friendly: JSON on stdout, logs on stderr, --pretty for humans.
The package entry point is `main`, wired up as the `cal-cli` console
script via pyproject.toml. See `cli.py` for the dispatch layer and the
per-concern modules (config, dates, events, format, auth, api) for the
pure-function pieces.
"""
from .cli import main

__all__ = ["main"]
