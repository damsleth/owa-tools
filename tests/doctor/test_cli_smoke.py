"""CLI smoke tests: help, version, JSON contract, exit codes."""
import json
import subprocess
import sys


def _run(args, env=None):
    cmd = [sys.executable, '-m', 'owa_doctor', *args]
    return subprocess.run(cmd, capture_output=True, text=True, env=env)


def test_help_runs():
    r = _run(['--help'])
    assert r.returncode == 0
    assert 'owa-doctor' in r.stdout


def test_help_subcommand():
    r = _run(['help'])
    assert r.returncode == 0
    assert 'owa-doctor' in r.stdout


def test_version_flag():
    r = _run(['--version'])
    assert r.returncode == 0
    assert r.stdout.strip().startswith('owa-doctor ')


def test_unknown_flag_fails():
    r = _run(['--frobnicate'])
    assert r.returncode == 2
    assert 'Unknown flag' in r.stderr
    assert 'Traceback' not in r.stderr


def test_no_tokens_runs_without_owa_piggy(tmp_path):
    """`--no-tokens` must not require owa-piggy on PATH and must
    still print a valid JSON report."""
    env = {
        'HOME': str(tmp_path),
        'PATH': str(tmp_path / 'empty-bin'),
    }
    (tmp_path / 'empty-bin').mkdir()
    r = _run(['--no-tokens'], env=env)
    # exit 2 because owa-piggy missing, but JSON should still be valid
    assert r.returncode == 2
    payload = json.loads(r.stdout)
    assert payload['owa_piggy']['installed'] is False
    assert payload['profiles'] == []
    assert 'Traceback' not in r.stderr
