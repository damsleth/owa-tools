"""Phase 6 agent contract tests.

Locks the suite-wide machine contract: structured errors, agent
envelopes, non-TTY confirm refusal, schema export, exit-code
taxonomy, and clean stdout/stderr separation.

These tests run against `owa_core.dispatch` with a toy spec, since
that is the path every Phase 3+ tool uses. Per-tool contract checks
land alongside their conversion to the dispatcher.
"""
from __future__ import annotations

import io
import json
import os

import pytest

from owa_core import dispatch, errors, tty


def _spec_with(handler, *, destructive=False):
    return dispatch.Spec(
        tool="owa-toy",
        version="1.2.3",
        commands=(
            dispatch.Command(
                name="ping",
                summary="echo a value",
                args=(dispatch.Arg("payload"),),
                handler=handler,
                destructive=destructive,
            ),
        ),
    )


# ---- 1: JSON on stdout by default ----

def test_default_output_is_json_on_stdout():
    spec = _spec_with(lambda args, flags, spec: {"echo": args["payload"]})
    out, err = io.StringIO(), io.StringIO()
    code = dispatch.run(spec, ["ping", "hi"], stdout=out, stderr=err)
    assert code == 0
    assert json.loads(out.getvalue()) == {"echo": "hi"}
    assert err.getvalue() == ""  # legacy success keeps stderr clean


# ---- 2: structured error option ----

def test_err_json_envelope_shape():
    def boom(args, flags, spec):
        raise errors.ScopeInsufficientError("nope", hint="re-consent")
    out, err = io.StringIO(), io.StringIO()
    code = dispatch.run(_spec_with(boom), ["ping", "x", "--err-json"],
                        stdout=out, stderr=err)
    assert code == int(errors.ExitCode.SCOPE_INSUFFICIENT)
    obj = json.loads(err.getvalue())
    assert obj["error"]["code"] == "SCOPE_INSUFFICIENT"
    assert obj["error"]["exit_code"] == 12
    assert obj["error"]["hint"] == "re-consent"
    assert obj["error"]["tool"] == "owa-toy"
    assert obj["error"]["command"] == "ping"


def test_err_json_via_env(monkeypatch):
    def boom(args, flags, spec):
        raise errors.NotFoundError("missing")
    monkeypatch.setenv("OWA_ERR_JSON", "1")
    out, err = io.StringIO(), io.StringIO()
    code = dispatch.run(_spec_with(boom), ["ping", "x"], stdout=out, stderr=err)
    assert code == 13
    json.loads(err.getvalue())  # parses


# ---- 3: stable exit codes ----

@pytest.mark.parametrize("exc, expected", [
    (errors.UsageError, 2),
    (errors.NetworkError, 10),
    (errors.AuthExpiredError, 11),
    (errors.ScopeInsufficientError, 12),
    (errors.NotFoundError, 13),
    (errors.RateLimitedError, 14),
    (errors.ConflictError, 15),
    (errors.InternalError, 20),
])
def test_exit_code_taxonomy_via_dispatch(exc, expected):
    def boom(args, flags, spec):
        raise exc("x")
    out, err = io.StringIO(), io.StringIO()
    code = dispatch.run(_spec_with(boom), ["ping", "v"], stdout=out, stderr=err)
    assert code == expected


# ---- 4: schema export ----

def test_schema_emits_full_spec():
    out, err = io.StringIO(), io.StringIO()
    spec = _spec_with(lambda *a, **kw: {})
    dispatch.run(spec, ["schema"], stdout=out, stderr=err)
    obj = json.loads(out.getvalue())
    assert obj["tool"] == "owa-toy"
    assert obj["version"] == "1.2.3"
    assert obj["commands"][0]["name"] == "ping"


def test_schema_specific_command():
    out, err = io.StringIO(), io.StringIO()
    spec = _spec_with(lambda *a, **kw: {})
    dispatch.run(spec, ["schema", "ping"], stdout=out, stderr=err)
    obj = json.loads(out.getvalue())
    assert obj["name"] == "ping"
    assert obj["args"][0]["name"] == "payload"


def test_help_json_round_trips_with_schema():
    out_help, _ = io.StringIO(), io.StringIO()
    out_schema, _ = io.StringIO(), io.StringIO()
    spec = _spec_with(lambda *a, **kw: {})
    dispatch.run(spec, ["--help", "--json"], stdout=out_help, stderr=io.StringIO())
    dispatch.run(spec, ["schema"], stdout=out_schema, stderr=io.StringIO())
    assert json.loads(out_help.getvalue()) == json.loads(out_schema.getvalue())


# ---- 5: agent envelope is opt-in ----

def test_agent_envelope_via_flag():
    spec = _spec_with(lambda args, flags, spec: [{"id": 1}, {"id": 2}])
    out, err = io.StringIO(), io.StringIO()
    dispatch.run(spec, ["ping", "x", "--agent"], stdout=out, stderr=err)
    obj = json.loads(out.getvalue())
    assert obj["_owa"]["tool"] == "owa-toy"
    assert obj["_owa"]["version"] == "1.2.3"
    assert obj["_owa"]["schema"] == 1
    assert obj["_owa"]["command"] == "ping"
    assert obj["data"] == [{"id": 1}, {"id": 2}]


def test_agent_envelope_via_env(monkeypatch):
    monkeypatch.setenv("OWA_AGENT", "1")
    spec = _spec_with(lambda args, flags, spec: {"k": "v"})
    out, err = io.StringIO(), io.StringIO()
    dispatch.run(spec, ["ping", "x"], stdout=out, stderr=err)
    obj = json.loads(out.getvalue())
    assert "_owa" in obj
    assert obj["data"] == {"k": "v"}


def test_legacy_callers_get_no_envelope():
    spec = _spec_with(lambda args, flags, spec: [{"a": 1}])
    out, err = io.StringIO(), io.StringIO()
    dispatch.run(spec, ["ping", "x"], stdout=out, stderr=err)
    obj = json.loads(out.getvalue())
    assert obj == [{"a": 1}]  # array, not envelope


# ---- 6: non-TTY confirm refusal ----

def test_confirm_refuses_off_tty(monkeypatch):
    class Fake:
        def isatty(self):
            return False
    monkeypatch.setattr("sys.stdin", Fake())
    monkeypatch.setattr("sys.stderr", Fake())
    with pytest.raises(errors.UsageError) as ei:
        tty.confirm("delete?")
    assert "non-interactive" in (ei.value.hint or "")


def test_confirm_force_bypasses_tty():
    assert tty.confirm("anything", force=True) is True


# ---- 7: clean stdout/stderr separation ----

def test_no_progress_text_on_stdout_for_handler():
    """Handlers may emit JSON only; nothing else should leak to stdout
    by default. Anything else they print is the handler's fault, not
    the dispatcher's.
    """
    spec = _spec_with(lambda args, flags, spec: {"x": 1})
    out, err = io.StringIO(), io.StringIO()
    dispatch.run(spec, ["ping", "v"], stdout=out, stderr=err)
    assert err.getvalue() == ""
    text = out.getvalue().strip()
    json.loads(text)
    assert "\n" not in text  # single JSON line, no extra


# ---- 8: usage errors hit the right exit code ----

def test_unknown_command_is_usage_error():
    spec = _spec_with(lambda *a, **kw: {})
    out, err = io.StringIO(), io.StringIO()
    code = dispatch.run(spec, ["nope"], stdout=out, stderr=err)
    assert code == int(errors.ExitCode.USAGE)
    assert "unknown command" in err.getvalue()


def test_missing_required_arg_is_usage_error():
    spec = _spec_with(lambda *a, **kw: {})
    spec.commands[0].args[0].required = True  # type: ignore[misc]
    out, err = io.StringIO(), io.StringIO()
    code = dispatch.run(spec, ["ping"], stdout=out, stderr=err)
    assert code == int(errors.ExitCode.USAGE)
