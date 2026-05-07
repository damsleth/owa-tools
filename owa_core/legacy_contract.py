"""Compatibility wrapper for handwritten consumer CLIs.

This module is intentionally small glue for the migration window where
consumer tools still use their original parsers. It provides the suite
contract that can be layered around those parsers without changing every
command implementation at once:

* ``schema`` and ``--help --json``
* opt-in ``--agent`` response envelopes
* opt-in ``--err-json`` error envelopes
* coarse exit-code normalization for legacy ``return 1`` paths
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
from typing import Callable


SCHEMA_VERSION = 1

_SPECS: dict[str, list[dict[str, object]]] = {
    "owa-cal": [
        {"name": "refresh"},
        {"name": "events"},
        {"name": "create", "destructive": True},
        {"name": "update", "destructive": True},
        {"name": "delete", "destructive": True},
        {"name": "categories"},
        {"name": "profiles"},
        {"name": "config"},
        {"name": "help"},
    ],
    "owa-mail": [
        {"name": "messages"},
        {"name": "show"},
        {"name": "send", "destructive": True},
        {"name": "reply", "destructive": True},
        {"name": "reply-all", "destructive": True},
        {"name": "forward", "destructive": True},
        {"name": "delete", "destructive": True},
        {"name": "move", "destructive": True},
        {"name": "mark", "destructive": True},
        {"name": "folders"},
        {"name": "refresh"},
        {"name": "config"},
        {"name": "help"},
    ],
    "owa-graph": [
        {"name": "GET"},
        {"name": "POST", "destructive": True},
        {"name": "PATCH", "destructive": True},
        {"name": "PUT", "destructive": True},
        {"name": "DELETE", "destructive": True},
        {"name": "batch", "destructive": True},
        {"name": "config"},
        {"name": "refresh"},
        {"name": "me"},
        {"name": "mail"},
        {"name": "calendar"},
        {"name": "files"},
        {"name": "users"},
        {"name": "teams"},
        {"name": "chats"},
        {"name": "presence"},
        {"name": "contacts"},
        {"name": "groups"},
        {"name": "planner"},
        {"name": "todo"},
        {"name": "sites"},
        {"name": "directory"},
        {"name": "help"},
    ],
    "owa-doctor": [
        {"name": "probe"},
    ],
    "owa-people": [
        {"name": "find"},
        {"name": "show"},
        {"name": "directory"},
        {"name": "me"},
        {"name": "contacts"},
        {"name": "refresh"},
        {"name": "config"},
        {"name": "help"},
    ],
    "owa-sched": [
        {"name": "availability"},
        {"name": "find-time"},
        {"name": "refresh"},
        {"name": "config"},
        {"name": "help"},
    ],
    "owa-drive": [
        {"name": "ls"},
        {"name": "show"},
        {"name": "get"},
        {"name": "put", "destructive": True},
        {"name": "rm", "destructive": True},
        {"name": "refresh"},
        {"name": "config"},
        {"name": "help"},
    ],
}

_GRAPH_GROUPS = {
    "me", "mail", "calendar", "files", "users", "teams", "chats",
    "presence", "contacts", "groups", "planner", "todo", "sites",
    "directory",
}


def schema(tool: str, version: str) -> dict[str, object]:
    commands = []
    for entry in _SPECS.get(tool, []):
        commands.append({
            "name": entry["name"],
            "summary": "",
            "args": [],
            "flags": [],
            "destructive": bool(entry.get("destructive")),
            "schema_version": SCHEMA_VERSION,
            "output_schema": None,
            "examples": [],
        })
    return {"tool": tool, "version": version, "commands": commands}


def handle_meta(
    tool: str,
    version: str,
    argv: list[str],
    *,
    print_help: Callable[[], None],
) -> int | None:
    if argv[:2] == ["--help", "--json"] or argv[:2] == ["--json", "--help"]:
        print(json.dumps(schema(tool, version), ensure_ascii=False))
        return 0
    if argv and argv[0] == "schema":
        spec = schema(tool, version)
        if len(argv) > 1:
            wanted = argv[1]
            for command in spec["commands"]:  # type: ignore[index]
                if command["name"] == wanted:
                    print(json.dumps(command, ensure_ascii=False))
                    return 0
            print(f"ERROR: unknown command: {wanted}", file=sys.stderr)
            return 2
        print(json.dumps(spec, ensure_ascii=False))
        return 0
    if len(argv) >= 2 and argv[1] in ("--help", "-h"):
        if tool == "owa-graph" and argv[0] in _GRAPH_GROUPS and "--json" not in argv[2:]:
            return None
        if "--json" in argv[2:]:
            spec = schema(tool, version)
            for command in spec["commands"]:  # type: ignore[index]
                if command["name"] == argv[0]:
                    print(json.dumps(command, ensure_ascii=False))
                    return 0
            print(f"ERROR: unknown command: {argv[0]}", file=sys.stderr)
            return 2
        print_help()
        return 0
    if argv and argv[0] in ("help", "--help", "-h"):
        if "--json" in argv[1:]:
            print(json.dumps(schema(tool, version), ensure_ascii=False))
        else:
            print_help()
        return 0
    return None


def agent_enabled(argv: list[str]) -> bool:
    return "--agent" in argv or os.environ.get("OWA_AGENT", "").strip() in (
        "1",
        "true",
        "yes",
    )


def err_json_enabled(argv: list[str]) -> bool:
    return "--err-json" in argv or os.environ.get("OWA_ERR_JSON", "").strip() in (
        "1",
        "true",
        "yes",
    )


def strip_contract_flags(argv: list[str]) -> list[str]:
    return [a for a in argv if a not in ("--agent", "--err-json")]


def classify_exit(code: int, stderr_text: str) -> tuple[int, str]:
    if code == 0:
        return 0, ""
    text = stderr_text.lower()
    if any(
        s in text
        for s in (
            "unknown command",
            "unknown flag",
            "requires a value",
            "requires an integer",
            " is required",
            "missing required",
            "unexpected argument",
            "refuses to run non-interactively",
            "refusing to prompt",
            "usage:",
        )
    ):
        return 2, "USAGE"
    if "auth expired" in text or "token refresh failed" in text or "re-seed" in text:
        return 11, "AUTH_EXPIRED"
    if "access denied" in text or "insufficient scope" in text:
        return 12, "SCOPE_INSUFFICIENT"
    if "not found" in text:
        return 13, "NOT_FOUND"
    if "rate limited" in text:
        return 14, "RATE_LIMITED"
    if "conflict" in text or "precondition" in text:
        return 15, "CONFLICT"
    if "network" in text or "timed out" in text:
        return 10, "NETWORK"
    return code, "INTERNAL" if code == 20 else "ERROR"


def emit_err_json(tool: str, command: str, code: int, error_code: str, stderr_text: str) -> None:
    message = stderr_text.strip().splitlines()[-1] if stderr_text.strip() else "command failed"
    if message.startswith("ERROR: "):
        message = message[7:]
    obj = {
        "error": {
            "code": error_code or "ERROR",
            "message": message,
            "hint": None,
            "tool": tool,
            "command": command,
            "exit_code": code,
        }
    }
    print(json.dumps(obj, ensure_ascii=False), file=sys.stderr)


def run_legacy(
    tool: str,
    version: str,
    argv: list[str],
    runner: Callable[[list[str]], int],
) -> int:
    agent = agent_enabled(argv)
    err_json = err_json_enabled(argv)
    filtered = strip_contract_flags(argv)
    command = filtered[0] if filtered else ""

    if agent and (
        (tool == "owa-drive" and command == "get" and "--out" not in filtered)
        or (tool == "owa-graph" and "--raw" in filtered)
    ):
        text = "agent mode cannot wrap raw binary stdout; write to a file or omit --raw"
        if err_json:
            emit_err_json(tool, command, 2, "USAGE", f"ERROR: {text}")
        else:
            print(f"ERROR: {text}", file=sys.stderr)
        return 2

    out_buf = io.StringIO() if agent else None
    err_buf = io.StringIO() if err_json else None
    try:
        with contextlib.redirect_stdout(out_buf or sys.stdout):
            with contextlib.redirect_stderr(err_buf or sys.stderr):
                try:
                    code = runner(filtered)
                except SystemExit as exc:
                    raw = exc.code
                    code = raw if isinstance(raw, int) else 1
    except BrokenPipeError:
        return 1

    stdout_text = out_buf.getvalue() if out_buf is not None else ""
    stderr_text = err_buf.getvalue() if err_buf is not None else ""
    code = int(code or 0)
    code, error_code = classify_exit(code, stderr_text)

    if code != 0:
        if err_json:
            emit_err_json(tool, command, code, error_code, stderr_text)
        return code

    if err_json and stderr_text:
        sys.stderr.write(stderr_text)

    if agent:
        text = stdout_text.strip()
        try:
            data = json.loads(text) if text else None
        except json.JSONDecodeError:
            data = text
        payload = {
            "_owa": {
                "tool": tool,
                "version": version,
                "schema": SCHEMA_VERSION,
                "command": command,
            },
            "data": data,
        }
        print(json.dumps(payload, ensure_ascii=False))
    return 0
