"""Cross-tool command contracts that do not require live Microsoft access."""
import json
import subprocess
import sys

TOOLS = (
    "owa_cal",
    "owa_mail",
    "owa_graph",
    "owa_doctor",
    "owa_people",
    "owa_sched",
    "owa_drive",
)


def _run_module(module, *args, env=None):
    return subprocess.run(
        [sys.executable, "-m", module, *args],
        capture_output=True,
        text=True,
        env=env,
    )


def test_all_tools_expose_help_and_version():
    versions = set()
    for module in TOOLS:
        help_result = _run_module(module, "--help")
        assert help_result.returncode == 0
        assert "Traceback" not in help_result.stderr

        version_result = _run_module(module, "--version")
        assert version_result.returncode == 0
        assert "Traceback" not in version_result.stderr
        versions.add(version_result.stdout.strip().split()[-1])

    assert len(versions) == 1


def test_owa_doctor_probe_no_tokens_is_json_without_broker(tmp_path):
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    result = _run_module(
        "owa_doctor",
        "probe",
        "--no-tokens",
        env={"HOME": str(tmp_path), "PATH": str(empty_bin)},
    )
    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["owa_piggy"]["installed"] is False
    assert payload["profiles"] == []
    assert "Traceback" not in result.stderr
