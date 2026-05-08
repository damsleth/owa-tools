"""Compatibility with the intended first-release command surface."""
import json
import subprocess
import sys


def _run_owa(*args, env=None):
    return subprocess.run(
        [sys.executable, "-m", "owa.cli", *args],
        capture_output=True,
        text=True,
        env=env,
    )


def test_umbrella_version_uses_suite_version():
    result = _run_owa("version")
    assert result.returncode == 0
    assert result.stdout.startswith("owa ")


def test_umbrella_list_is_json():
    result = _run_owa("list")
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert {row["tool"] for row in payload} >= {"owa-cal", "owa-mail", "owa-graph"}


def test_umbrella_doctor_forwards_to_probe(tmp_path):
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    env = {"HOME": str(tmp_path), "PATH": str(empty_bin)}
    result = _run_owa("doctor", "--no-tokens", env=env)
    assert result.returncode == 13
    assert "owa-doctor not on PATH" in result.stderr
