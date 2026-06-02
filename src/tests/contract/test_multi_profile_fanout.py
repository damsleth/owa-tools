"""End-to-end multi-profile fan-out, exercised through each real tool binary.

No internals are mocked. With owa-piggy absent from PATH, every profile's auth
fails identically, which drives the all-fail merge path through each tool's
actual ``main() -> run_with_output_modes(fan_out_profiles=True)`` wiring. That
proves, per tool, that repeated ``--profile`` is parsed, fanned out, isolated
per profile, and merged into the documented envelope - the wiring the unit
tests in ``tests/core/test_modes.py`` exercise only against a fake dispatcher.

The success-merge shape (one profile returning data) is covered in-process with
mocked auth in ``tests/mail/test_multi_profile.py``; here we lean on the
deterministic broker-missing failure so the test needs no network and no mocks.
"""
import json
import subprocess
import sys

import pytest

# (module, read-command argv): a command with no required args that reaches
# auth, so the broker-missing path turns into a clean per-profile auth failure.
FANNING_TOOLS = [
    ("owa_mail", ["messages"]),
    ("owa_cal", ["events"]),
    ("owa_graph", ["GET", "/me"]),
    ("owa_people", ["me"]),
    ("owa_drive", ["ls"]),
    ("owa_todo", ["tasks"]),
    ("owa_planner", ["plans"]),
    ("owa_sites", ["site"]),
    ("owa_sched", ["availability", "--who", "test@example.com"]),
]

_IDS = [module for module, _ in FANNING_TOOLS]


@pytest.fixture
def broker_missing_env(tmp_path):
    """HOME under tmp_path and a PATH with no owa-piggy, so every mint fails."""
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    return {"HOME": str(tmp_path), "PATH": str(empty_bin)}


def _run(module, argv, env):
    return subprocess.run(
        [sys.executable, "-m", module, *argv],
        capture_output=True,
        text=True,
        env=env,
    )


@pytest.mark.parametrize("module,cmd", FANNING_TOOLS, ids=_IDS)
def test_repeated_profile_fans_out_and_merges_json(module, cmd, broker_missing_env):
    tool = module.replace("_", "-")
    result = _run(
        module, ["--profile", "alpha", "--profile", "beta", *cmd], broker_missing_env
    )

    # All profiles fail auth (broker missing) -> all-fail merge -> exit 1.
    assert result.returncode == 1, (
        f"{module}: rc={result.returncode}\nstdout={result.stdout!r}\n"
        f"stderr={result.stderr!r}"
    )
    payload = json.loads(result.stdout)
    assert payload["_owa"]["suite"] == "owa-tools"
    assert payload["_owa"]["tool"] == tool
    assert payload["_owa"]["profiles"] == ["alpha", "beta"]

    results = payload["results"]
    assert [r["profile"] for r in results] == ["alpha", "beta"]
    assert all(r["ok"] is False for r in results)
    # owa-piggy-missing surfaces as AuthExpiredError (exit code 11).
    assert all(r["exit_code"] == 11 for r in results)
    assert all(r["error"] for r in results)
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize("module,cmd", FANNING_TOOLS, ids=_IDS)
def test_repeated_profile_pretty_labels_each_profile(module, cmd, broker_missing_env):
    result = _run(
        module,
        ["--profile", "alpha", "--profile", "beta", *cmd, "--pretty"],
        broker_missing_env,
    )
    assert result.returncode == 1
    assert "=== profile: alpha (FAILED) ===" in result.stdout
    assert "=== profile: beta (FAILED) ===" in result.stdout


def test_duplicate_profile_warns_and_collapses_to_single(broker_missing_env):
    """A repeated alias warns once and de-dups, so two identical --profile
    values take the single-profile path (legacy shape, no `results` wrapper)."""
    result = _run(
        "owa_mail", ["--profile", "x", "--profile", "x", "messages"], broker_missing_env
    )
    assert "warning: duplicate --profile x ignored" in result.stderr
    # One distinct profile -> N<=1 path -> single-profile auth failure (exit 11),
    # NOT the fan-out envelope.
    assert result.returncode == 11
    assert '"results"' not in result.stdout


def test_doctor_opts_out_of_fan_out(broker_missing_env):
    """owa-doctor sets fan_out_profiles=False: repeated --profile must NOT
    produce the fan-out `results` envelope. --no-tokens keeps it deterministic
    without a broker."""
    result = _run(
        "owa_doctor",
        ["probe", "--no-tokens", "--profile", "a", "--profile", "b"],
        broker_missing_env,
    )
    payload = json.loads(result.stdout)
    assert "results" not in payload  # not the fan-out shape
    # It is still doctor's own probe report.
    assert "owa_piggy" in payload
    assert "profiles" in payload
