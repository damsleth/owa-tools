"""owa-doctor - health-check meta-CLI for the owa-* suite.

Probes owa-piggy and every sibling owa-* CLI on PATH, reports token
age and profile health. JSON on stdout, --pretty for humans. Mirrors
the pattern used by owa-cal/owa-mail: stdlib only, pipe-friendly.
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
            return version('owa-doctor')
        except PackageNotFoundError:
            pass
    except ImportError:
        pass
    return 'unknown'


__version__ = _read_version()

from .cli import main  # noqa: E402

__all__ = ["main", "__version__"]
