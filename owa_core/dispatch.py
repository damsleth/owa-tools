"""Declarative subcommand specs and schema generation.

Public surface:
    Spec(tool, version, commands)
    Command(name, args, flags, handler, output_schema, examples)
    Arg(name, type, required=False, help="")
    Flag(name, type, default=None, help="", choices=None)
    run(spec, argv) -> int

The dispatcher owns:
    - argv parsing (replaces hand-rolled while-args loops in every CLI)
    - usage errors (uniform messages, exit code 2)
    - --help text generation
    - --help --json schema export
    - <tool> schema [command] subcommand auto-wiring
    - --agent / OWA_AGENT envelope wrapping
    - --err-json / OWA_ERR_JSON error envelope
    - non-TTY confirm refusal for destructive commands

Each consumer CLI declares one Spec and calls run(). Behavior is
identical across tools.
"""
from __future__ import annotations

import json as _json
import os
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

from .errors import ExitCode, OwaError, UsageError, emit


@dataclass
class Arg:
    name: str
    type: type = str
    required: bool = False
    help: str = ""


@dataclass
class Flag:
    name: str
    type: type = str
    default: Any = None
    help: str = ""
    choices: tuple[str, ...] | None = None


@dataclass
class Command:
    name: str
    args: Sequence[Arg] = field(default_factory=tuple)
    flags: Sequence[Flag] = field(default_factory=tuple)
    handler: Callable[..., Any] | None = None
    output_schema: dict | None = None
    examples: Sequence[str] = field(default_factory=tuple)
    destructive: bool = False
    schema_version: int = 1
    summary: str = ""


@dataclass
class Spec:
    tool: str
    version: str
    commands: Sequence[Command]


# ---------- shared flags injected on every command ----------

_GLOBAL_FLAGS: tuple[Flag, ...] = (
    Flag(name="--help", type=bool, default=False, help="show help and exit"),
    Flag(name="--agent", type=bool, default=False, help="wrap output in agent envelope"),
    Flag(name="--err-json", type=bool, default=False, help="render errors as JSON"),
    Flag(name="--pretty", type=bool, default=False, help="human-readable output"),
    Flag(name="--yes", type=bool, default=False, help="assume yes for destructive prompts"),
    Flag(name="--confirm", type=bool, default=False, help="alias for --yes"),
)


def _agent_enabled(parsed_flags: dict[str, Any]) -> bool:
    if parsed_flags.get("--agent"):
        return True
    return os.environ.get("OWA_AGENT", "").strip() in ("1", "true", "yes")


def _coerce(value: str, kind: type, name: str) -> Any:
    if kind is bool:
        if value.lower() in ("1", "true", "yes", "on"):
            return True
        if value.lower() in ("0", "false", "no", "off"):
            return False
        raise UsageError(f"invalid boolean for {name}: {value!r}")
    try:
        return kind(value)
    except (TypeError, ValueError) as e:
        raise UsageError(f"invalid value for {name}: {value!r} ({e})") from e


def _flag_lookup(cmd: Command) -> dict[str, Flag]:
    out: dict[str, Flag] = {}
    for f in _GLOBAL_FLAGS:
        out[f.name] = f
    for f in cmd.flags:
        out[f.name] = f
    return out


def _parse_argv(cmd: Command, argv: list[str]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (positional_args, flags). Raises UsageError on bad input."""
    flag_lookup = _flag_lookup(cmd)
    flags: dict[str, Any] = {f.name: f.default for f in flag_lookup.values()}
    positional: list[str] = []
    i = 0
    while i < len(argv):
        token = argv[i]
        if token == "--":
            positional.extend(argv[i + 1:])
            break
        if token.startswith("--"):
            name, _, inline = token.partition("=")
            if name not in flag_lookup:
                raise UsageError(f"unknown flag: {name}")
            f = flag_lookup[name]
            if f.type is bool:
                if inline:
                    flags[name] = _coerce(inline, bool, name)
                else:
                    flags[name] = True
                i += 1
                continue
            if inline:
                value = inline
            else:
                if i + 1 >= len(argv):
                    raise UsageError(f"flag {name} requires a value")
                value = argv[i + 1]
                i += 1
            if f.choices and value not in f.choices:
                raise UsageError(
                    f"invalid choice for {name}: {value!r}",
                    hint=f"allowed: {', '.join(f.choices)}",
                )
            flags[name] = _coerce(value, f.type, name)
            i += 1
            continue
        positional.append(token)
        i += 1
    parsed_args: dict[str, Any] = {}
    for idx, arg in enumerate(cmd.args):
        if idx < len(positional):
            parsed_args[arg.name] = _coerce(positional[idx], arg.type, arg.name)
        elif arg.required:
            raise UsageError(f"missing required argument: {arg.name}")
        else:
            parsed_args[arg.name] = None
    extra = positional[len(cmd.args):]
    if extra:
        raise UsageError(f"unexpected arguments: {' '.join(extra)}")
    return parsed_args, flags


# ---------- help / schema rendering ----------

def _help_text(spec: Spec, cmd: Command | None) -> str:
    if cmd is None:
        lines = [f"{spec.tool} {spec.version}", "", "commands:"]
        for c in spec.commands:
            lines.append(f"  {c.name:<14} {c.summary}")
        lines.append("")
        lines.append(f"use `{spec.tool} <command> --help` for command details")
        return "\n".join(lines)
    parts = [f"{spec.tool} {cmd.name}"]
    if cmd.summary:
        parts.append("")
        parts.append(cmd.summary)
    if cmd.args:
        parts.append("")
        parts.append("arguments:")
        for a in cmd.args:
            req = " (required)" if a.required else ""
            parts.append(f"  {a.name:<14} {a.help}{req}")
    if cmd.flags:
        parts.append("")
        parts.append("flags:")
        for f in cmd.flags:
            parts.append(f"  {f.name:<18} {f.help}")
    if cmd.examples:
        parts.append("")
        parts.append("examples:")
        for ex in cmd.examples:
            parts.append(f"  {ex}")
    return "\n".join(parts)


def _command_schema(cmd: Command) -> dict[str, Any]:
    return {
        "name": cmd.name,
        "summary": cmd.summary,
        "args": [
            {"name": a.name, "type": a.type.__name__, "required": a.required, "help": a.help}
            for a in cmd.args
        ],
        "flags": [
            {
                "name": f.name,
                "type": f.type.__name__,
                "default": f.default,
                "help": f.help,
                "choices": list(f.choices) if f.choices else None,
            }
            for f in cmd.flags
        ],
        "destructive": cmd.destructive,
        "schema_version": cmd.schema_version,
        "output_schema": cmd.output_schema,
        "examples": list(cmd.examples),
    }


def _spec_schema(spec: Spec) -> dict[str, Any]:
    return {
        "tool": spec.tool,
        "version": spec.version,
        "commands": [_command_schema(c) for c in spec.commands],
    }


# ---------- envelope ----------

def _wrap_envelope(spec: Spec, cmd: Command, value: Any) -> dict[str, Any]:
    return {
        "_owa": {
            "tool": spec.tool,
            "version": spec.version,
            "schema": cmd.schema_version,
            "command": cmd.name,
        },
        "data": value,
    }


# ---------- run ----------

def _find_command(spec: Spec, name: str) -> Command | None:
    for c in spec.commands:
        if c.name == name:
            return c
    return None


def run(spec: Spec, argv: list[str], *, stdout=None, stderr=None) -> int:
    """Parse argv, dispatch to the matching command, render output.

    Returns the exit code. Handlers may return:
        - int: used as the exit code, no JSON output emitted
        - dict / list / None: rendered as JSON on stdout, exit 0
        - any other value: rendered as JSON on stdout, exit 0
    """
    out = stdout if stdout is not None else sys.stdout
    err = stderr if stderr is not None else sys.stderr
    if not argv:
        out.write(_help_text(spec, None) + "\n")
        return 0
    head = argv[0]
    if head in ("--help", "-h"):
        if "--json" in argv[1:]:
            out.write(_json.dumps(_spec_schema(spec), ensure_ascii=False) + "\n")
        else:
            out.write(_help_text(spec, None) + "\n")
        return 0
    if head == "--version":
        out.write(f"{spec.tool} {spec.version}\n")
        return 0
    if head == "schema":
        if len(argv) >= 2:
            cmd = _find_command(spec, argv[1])
            if cmd is None:
                err.write(f"ERROR: unknown command: {argv[1]}\n")
                return int(ExitCode.USAGE)
            out.write(_json.dumps(_command_schema(cmd), ensure_ascii=False) + "\n")
            return 0
        out.write(_json.dumps(_spec_schema(spec), ensure_ascii=False) + "\n")
        return 0

    cmd = _find_command(spec, head)
    if cmd is None:
        err.write(f"ERROR: unknown command: {head}\n")
        return int(ExitCode.USAGE)

    rest = argv[1:]
    try:
        args, flags = _parse_argv(cmd, rest)
    except UsageError as e:
        return emit(e, tool=spec.tool, command=cmd.name,
                    err_json=_should_err_json(rest), stream=err)
    if flags.get("--help"):
        if flags.get("--agent") or "--json" in rest:
            out.write(_json.dumps(_command_schema(cmd), ensure_ascii=False) + "\n")
        else:
            out.write(_help_text(spec, cmd) + "\n")
        return 0
    if cmd.handler is None:
        err.write(f"ERROR: command {cmd.name} has no handler\n")
        return int(ExitCode.INTERNAL)

    try:
        result = cmd.handler(args=args, flags=flags, spec=spec)
    except OwaError as e:
        return emit(e, tool=spec.tool, command=cmd.name,
                    err_json=flags.get("--err-json"), stream=err)
    except SystemExit:
        raise
    except Exception as e:
        wrapped = OwaError(f"internal error: {e}")
        wrapped.code = ExitCode.INTERNAL
        wrapped.error_code = "INTERNAL"
        return emit(wrapped, tool=spec.tool, command=cmd.name,
                    err_json=flags.get("--err-json"), stream=err)

    if isinstance(result, int):
        return result
    if result is None:
        return 0
    payload = _wrap_envelope(spec, cmd, result) if _agent_enabled(flags) else result
    out.write(_json.dumps(payload, ensure_ascii=False) + "\n")
    return 0


def _should_err_json(rest: list[str]) -> bool:
    if "--err-json" in rest:
        return True
    return os.environ.get("OWA_ERR_JSON", "").strip() in ("1", "true", "yes")
