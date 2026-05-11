#!/usr/bin/env python3
"""Reject committed source that contains token-shaped secrets.

The scanner is deliberately shape-based and stdlib-only. It ignores generated
and local-only directories, while still scanning runtime code, tests, docs, and
GitHub workflows.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from owa_core.secrets import find_secret_shapes  # noqa: E402

EXCLUDED_PARTS = {
    '.git',
    '.mypy_cache',
    '.pytest_cache',
    '.ruff_cache',
    '.venv',
    '__pycache__',
    'build',
    'dist',
    'owa_tools.egg-info',
}
EXCLUDED_SUFFIXES = {'.pyc', '.pyo', '.so', '.dylib', '.png', '.jpg', '.jpeg', '.gif'}


def is_scanned(path: Path) -> bool:
    rel = path.relative_to(REPO_ROOT)
    if any(part in EXCLUDED_PARTS for part in rel.parts):
        return False
    if rel.parts and rel.parts[0] == '.plans':
        return False
    if path.suffix.lower() in EXCLUDED_SUFFIXES:
        return False
    return path.is_file()


def iter_files():
    for path in REPO_ROOT.rglob('*'):
        if is_scanned(path):
            yield path


def read_text(path: Path):
    try:
        return path.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        return None


def main() -> int:
    failures = []
    for path in iter_files():
        text = read_text(path)
        if text is None:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            for finding in find_secret_shapes(line):
                failures.append((path.relative_to(REPO_ROOT), lineno, finding.kind))

    if not failures:
        print('no-secret check: OK')
        return 0

    print('no-secret check: FAIL', file=sys.stderr)
    for path, lineno, kind in failures:
        print(f'  {path}:{lineno}: {kind}', file=sys.stderr)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
