"""owa-sched - scheduling assistant for Outlook / Microsoft 365.

Wraps Graph `POST /me/calendar/getSchedule` for free/busy lookups and
naive multi-attendee slot finding. Pipe-friendly: JSON on stdout,
logs on stderr, --pretty for humans. Sibling of owa-cal/owa-mail.
"""


def _read_version():
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
    try:
        from importlib.metadata import PackageNotFoundError, version
        try:
            return version('owa-sched')
        except PackageNotFoundError:
            pass
    except ImportError:
        pass
    return 'unknown'


__version__ = _read_version()

from .cli import main  # noqa: E402

__all__ = ["main", "__version__"]
