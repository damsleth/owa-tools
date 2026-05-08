"""Suite version helpers.

`owa-tools` ships as one distribution with several console scripts. Keep
version lookup centralized so every binary reports the same installed version.
"""
from __future__ import annotations

import re
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

DIST_NAME = "owa-tools"
FALLBACK_VERSION = "0.0.0.dev0"


def _version_from_root_pyproject() -> str | None:
    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    if not pyproject.is_file():
        return None
    pattern = re.compile(r'\s*version\s*=\s*"([^"]+)"')
    try:
        for line in pyproject.read_text(encoding="utf-8").splitlines():
            match = pattern.match(line)
            if match:
                return match.group(1)
    except OSError:
        return None
    return None


def suite_version() -> str:
    """Return the installed `owa-tools` distribution version.

    In a source checkout, editable metadata may not exist yet, so fall back to
    the root `pyproject.toml`. This keeps `python -m owa_cal --version` useful
    before installation without reviving per-tool version drift.
    """
    try:
        return version(DIST_NAME)
    except PackageNotFoundError:
        return _version_from_root_pyproject() or FALLBACK_VERSION


def binary_version(binary_name: str) -> str:
    return f"{binary_name} {suite_version()}"
