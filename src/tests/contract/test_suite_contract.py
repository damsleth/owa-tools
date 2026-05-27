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
    "owa_todo",
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


def test_all_tools_expose_schema_and_json_help():
    for module in TOOLS:
        schema_result = _run_module(module, "schema")
        assert schema_result.returncode == 0
        schema = json.loads(schema_result.stdout)
        assert schema["suite"] == "owa-tools"
        assert schema["commands"]
        assert "Traceback" not in schema_result.stderr

        help_json_result = _run_module(module, "--help", "--json")
        assert help_json_result.returncode == 0
        assert json.loads(help_json_result.stdout)["tool"] == schema["tool"]


def test_schema_subcommand_filters_one_command():
    result = _run_module("owa_mail", "schema", "messages")
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert [command["name"] for command in payload["commands"]] == ["messages"]


def test_destructive_commands_declare_confirmation_metadata():
    expected = {
        "owa_cal": {"delete"},
        "owa_mail": {"delete"},
        "owa_drive": {"rm"},
        "owa_todo": {"delete"},
    }
    for module, command_names in expected.items():
        result = _run_module(module, "schema")
        assert result.returncode == 0
        commands = {row["name"]: row for row in json.loads(result.stdout)["commands"]}
        for name in command_names:
            row = commands[name]
            assert row["mutates"] is True
            assert row["destructive"] is True
            assert row["confirmation"] == {"flag": "--confirm"}
            assert row["idempotent"] is False


def test_every_subcommand_supports_dash_dash_help():
    """Every command in COMMAND_SCHEMA must respond to `--help` with exit 0
    and stdout that mentions the command name. Per-subcommand help is the
    agent-facing surface most reach for first (`<tool> <cmd> --help`) and
    used to silently fail with `Unknown flag: --help`.
    """
    for module in TOOLS:
        schema = json.loads(_run_module(module, "schema").stdout)
        for command in schema["commands"]:
            name = command["name"]
            result = _run_module(module, name, "--help")
            assert result.returncode == 0, (
                f"{module} {name} --help failed: {result.stderr!r}"
            )
            assert "Traceback" not in result.stderr
            assert f"{schema['tool']} {name}" in result.stdout, (
                f"{module} {name} --help missing usage line: {result.stdout!r}"
            )


def test_subcommand_help_works_with_short_form():
    """`<tool> <cmd> -h` should match `--help`."""
    for tool, cmd in (("owa_cal", "events"), ("owa_mail", "messages")):
        long = _run_module(tool, cmd, "--help")
        short = _run_module(tool, cmd, "-h")
        assert long.returncode == 0
        assert short.returncode == 0
        assert long.stdout == short.stdout


def test_subcommand_help_renders_required_flag_marker():
    result = _run_module("owa_cal", "create", "--help")
    assert result.returncode == 0
    assert "--subject" in result.stdout
    assert "(required)" in result.stdout


def test_subcommand_help_renders_destructive_notes():
    result = _run_module("owa_drive", "rm", "--help")
    assert result.returncode == 0
    assert "destructive" in result.stdout
    assert "--confirm" in result.stdout


def test_umbrella_schema_has_real_tool_entries():
    result = _run_module("owa", "schema", "--tool", "owa-mail")
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert len(payload) == 1
    assert payload[0]["schema_supported"] is True
    assert payload[0]["schema"]["tool"] == "owa-mail"


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


def test_err_json_maps_auth_failure_to_structured_stderr(tmp_path):
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    result = _run_module(
        "owa_mail",
        "--err-json",
        "messages",
        env={"HOME": str(tmp_path), "PATH": str(empty_bin)},
    )

    assert result.returncode == 11
    assert result.stdout == ""
    payload = json.loads(result.stderr)
    assert payload["error"]["code"] == "AUTH_EXPIRED"
    assert payload["error"]["tool"] == "owa-mail"
    assert payload["error"]["command"] == "messages"
    assert "owa-piggy" in payload["error"]["message"]


def test_agent_mode_wraps_successful_json_output():
    result = _run_module("owa_mail", "--agent", "schema", "messages")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["_owa"]["tool"] == "owa-mail"
    assert payload["_owa"]["command"] == "schema"
    assert payload["data"]["commands"][0]["name"] == "messages"
