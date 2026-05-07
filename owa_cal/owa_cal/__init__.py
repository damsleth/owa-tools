"""owa-cal - calendar CLI for Outlook / Microsoft 365.

Pipe-friendly: JSON on stdout, logs on stderr, --pretty for humans.
The package entry point is `main`, wired up as the `owa-cal` console
script via pyproject.toml. See `cli.py` for the dispatch layer and the
per-concern modules (config, dates, events, format, auth, api) for the
pure-function pieces.

`__version__` reads the installed distribution metadata so the value
always matches whatever `pyproject.toml` declared at install time. In a
bare repo checkout (no install), that lookup fails; we fall back to
scraping the adjacent `pyproject.toml` so `python3 -m owa_cal` still
reports a real version. Mirrors owa-piggy's pattern.
"""


def _read_version():
    # Repo-checkout path first: when running from a local clone, the
    # source pyproject.toml is the canonical version. Checking
    # importlib.metadata first would pick up any stale `pip install`
    # from a user site-packages and report a version older than the
    # code actually running.
    try:
        import re
        from pathlib import Path
        pp = Path(__file__).resolve().parent.parent / 'pyproject.toml'
        if pp.is_file():
            for line in pp.read_text().splitlines():
                m = re.match(r'\s*version\s*=\s*"([^"]+)"', line)
                if m:
                    return m.group(1)
    except Exception:
        pass
    # Installed path: brew/pipx/pip. No sibling pyproject.toml exists.
    try:
        from importlib.metadata import PackageNotFoundError, version
        try:
            return version('owa-cal')
        except PackageNotFoundError:
            pass
    except ImportError:
        pass
    return 'unknown'


__version__ = _read_version()

# Defined after __version__ so cli.py can safely `from . import __version__`.
from .cli import main  # noqa: E402

__all__ = ["main", "__version__"]
