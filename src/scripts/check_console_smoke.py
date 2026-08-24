#!/usr/bin/env python3
"""Install the built wheel into a fresh venv and smoke-test console scripts."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import venv
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

TOOLS = (
    'owa-cal',
    'owa-mail',
    'owa-graph',
    'owa-doctor',
    'owa-people',
    'owa-sched',
    'owa-drive',
    'owa-todo',
    'owa-planner',
    'owa-sites',
    'owa-teams',
    'owa-vids',
    'owa-ado',
    'owa-swodp',
)


def _bin(venv_dir, name):
    return venv_dir / ('Scripts' if sys.platform == 'win32' else 'bin') / name


def _latest_wheel():
    wheels = sorted((REPO_ROOT / 'dist').glob('owa_tools-*.whl'))
    return wheels[-1] if wheels else None


def _run(args, *, env=None):
    return subprocess.run(args, capture_output=True, text=True, check=False, timeout=20, env=env)


def _expect_json(stdout, label):
    try:
        return json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(f'{label}: stdout was not JSON: {exc}') from exc


def smoke(venv_dir, wheel):
    failures = []
    subprocess.run(
        [str(_bin(venv_dir, 'python')), '-m', 'pip', 'install', '--no-index', str(wheel)],
        check=True,
        timeout=60,
    )
    smoke_env = {
        **os.environ,
        'PATH': str(_bin(venv_dir, 'python').parent),
        'HOME': str(venv_dir / 'home'),
    }

    for tool in TOOLS:
        for args in (['--help'], ['--version'], ['schema']):
            proc = _run([str(_bin(venv_dir, tool)), *args], env=smoke_env)
            if proc.returncode != 0:
                failures.append(f'{tool} {" ".join(args)} exited {proc.returncode}: {proc.stderr}')
                continue
            if args == ['schema']:
                payload = _expect_json(proc.stdout, f'{tool} schema')
                if payload.get('tool') != tool:
                    failures.append(f'{tool} schema reported {payload.get("tool")!r}')

    proc = _run([str(_bin(venv_dir, 'owa')), 'version'], env=smoke_env)
    if proc.returncode != 0 or not proc.stdout.startswith('owa '):
        failures.append(f'owa version failed: rc={proc.returncode} stdout={proc.stdout!r}')

    proc = _run([str(_bin(venv_dir, 'owa')), 'list'], env=smoke_env)
    if proc.returncode != 0:
        failures.append(f'owa list exited {proc.returncode}: {proc.stderr}')
    else:
        rows = _expect_json(proc.stdout, 'owa list')
        installed = {row.get('tool'): row.get('installed') for row in rows}
        for tool in TOOLS:
            if installed.get(tool) is not True:
                failures.append(f'owa list did not report installed tool {tool}')

    proc = _run([str(_bin(venv_dir, 'owa')), 'schema'], env=smoke_env)
    if proc.returncode != 0:
        failures.append(f'owa schema exited {proc.returncode}: {proc.stderr}')
    else:
        rows = _expect_json(proc.stdout, 'owa schema')
        for row in rows:
            if row.get('installed') and row.get('schema_supported') is not True:
                failures.append(f'owa schema missing schema for {row.get("tool")}')

    proc = _run([str(_bin(venv_dir, 'owa-doctor')), 'probe', '--no-tokens'], env=smoke_env)
    if proc.returncode != 2:
        failures.append(f'owa-doctor probe --no-tokens expected rc=2 without broker, got {proc.returncode}')
    else:
        report = _expect_json(proc.stdout, 'owa-doctor probe --no-tokens')
        if report.get('owa_piggy', {}).get('installed') is not False:
            failures.append('owa-doctor probe did not report missing owa-piggy in clean venv')

    return failures


def main(argv=None):
    argv = list(argv or sys.argv[1:])
    wheel = Path(argv[0]) if argv else _latest_wheel()
    if wheel is None or not wheel.is_file():
        print('console smoke: FAIL no wheel found', file=sys.stderr)
        return 1
    with tempfile.TemporaryDirectory(prefix='owa-tools-smoke-') as tmp:
        venv_dir = Path(tmp) / 'venv'
        venv.EnvBuilder(with_pip=True).create(venv_dir)
        failures = smoke(venv_dir, wheel)
    if not failures:
        print('console smoke: OK')
        return 0
    print('console smoke: FAIL', file=sys.stderr)
    for failure in failures:
        print(f'  {failure}', file=sys.stderr)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
