#!/usr/bin/env python3
"""Inspect built distributions for local junk and secret-shaped content."""
from __future__ import annotations

import sys
import tarfile
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from owa_core.secrets import find_secret_shapes  # noqa: E402

FORBIDDEN_PARTS = {
    '.coverage',
    '.env',
    '.git',
    '.mypy_cache',
    '.plans',
    '.pytest_cache',
    '.ruff_cache',
    '.venv',
    '__pycache__',
    'htmlcov',
}
FORBIDDEN_SUFFIXES = {
    '.pyc',
    '.pyo',
    '.swp',
}
TEXT_SUFFIXES = {
    '',
    '.cfg',
    '.ini',
    '.json',
    '.md',
    '.py',
    '.toml',
    '.txt',
    '.yml',
    '.yaml',
}


def _bad_path_reason(name):
    path = Path(name)
    if any(part in FORBIDDEN_PARTS for part in path.parts):
        return 'forbidden path component'
    if path.suffix.lower() in FORBIDDEN_SUFFIXES:
        return 'forbidden file suffix'
    if path.name in {'coverage.json'}:
        return 'forbidden generated file'
    return None


def _text_findings(name, data):
    if Path(name).suffix.lower() not in TEXT_SUFFIXES:
        return []
    try:
        text = data.decode('utf-8')
    except UnicodeDecodeError:
        return []
    findings = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for finding in find_secret_shapes(line):
            findings.append((lineno, finding.kind))
    return findings


def _inspect_zip(path):
    failures = []
    with zipfile.ZipFile(path) as zf:
        for info in zf.infolist():
            reason = _bad_path_reason(info.filename)
            if reason:
                failures.append((info.filename, reason))
            if info.is_dir():
                continue
            data = zf.read(info.filename)
            for lineno, kind in _text_findings(info.filename, data):
                failures.append((f'{info.filename}:{lineno}', f'secret-shaped {kind}'))
    return failures


def _inspect_tar(path):
    failures = []
    with tarfile.open(path) as tf:
        for member in tf.getmembers():
            reason = _bad_path_reason(member.name)
            if reason:
                failures.append((member.name, reason))
            if not member.isfile():
                continue
            fileobj = tf.extractfile(member)
            if fileobj is None:
                continue
            data = fileobj.read()
            for lineno, kind in _text_findings(member.name, data):
                failures.append((f'{member.name}:{lineno}', f'secret-shaped {kind}'))
    return failures


def inspect_artifact(path):
    if zipfile.is_zipfile(path):
        return _inspect_zip(path)
    if tarfile.is_tarfile(path):
        return _inspect_tar(path)
    return [(str(path), 'unsupported artifact type')]


def _default_artifacts():
    dist = REPO_ROOT / 'dist'
    if not dist.is_dir():
        return []
    return sorted(path for path in dist.iterdir() if path.suffix in {'.whl', '.gz', '.zip'})


def main(argv=None) -> int:
    argv = list(argv or sys.argv[1:])
    artifacts = [Path(arg) for arg in argv] if argv else _default_artifacts()
    if not artifacts:
        print('artifact check: FAIL no artifacts found', file=sys.stderr)
        return 1

    failures = []
    for artifact in artifacts:
        for name, reason in inspect_artifact(artifact):
            failures.append((artifact, name, reason))

    if not failures:
        print('artifact check: OK')
        return 0

    print('artifact check: FAIL', file=sys.stderr)
    for artifact, name, reason in failures:
        print(f'  {artifact}: {name}: {reason}', file=sys.stderr)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
