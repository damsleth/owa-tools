"""Umbrella `owa` binary. Discovery only; not a full dispatcher.

Subcommands:
  owa list         List installed consumer CLIs and their versions
                   (JSON by default; --pretty for a table).
  owa schema       Aggregate schemas from each consumer CLI.
  owa doctor       Forward to `owa-doctor probe`.
  owa version      Print the umbrella version.

Real work lives in the consumer CLIs (owa-cal, owa-mail, ...).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from owa_core.modes import is_doctor_invocation

from . import __version__

CONSUMERS = (
    "owa-cal",
    "owa-mail",
    "owa-graph",
    "owa-doctor",
    "owa-people",
    "owa-sched",
    "owa-drive",
)


def _which(name: str) -> str | None:
    for base in (
        Path(sys.argv[0]).parent,
        Path(sys.argv[0]).resolve().parent,
        Path(sys.executable).parent,
        Path(sys.executable).resolve().parent,
    ):
        candidate = base / name
        if candidate.exists():
            return str(candidate)
    found = shutil.which(name)
    if found:
        return found
    return None


def _version_of(binary: str) -> str | None:
    """Best-effort version lookup. Tries `--version`, falls back to the
    first line of `--help`. Returns None on failure.

    Several owa-* CLIs do not implement --version yet; that's tracked as
    Phase 6 work in the implementation plan. This function works against
    today's state."""
    path = _which(binary)
    if path is None:
        return None

    def _run(args: list[str]) -> str | None:
        try:
            out = subprocess.run(
                [path, *args],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (subprocess.TimeoutExpired, OSError):
            return None
        return (out.stdout or out.stderr or "").strip() or None

    text = _run(["--version"])
    if text and not _looks_like_error(text):
        return text.splitlines()[0]
    text = _run(["--help"])
    if text:
        return text.splitlines()[0]
    return None


def _looks_like_error(text: str) -> bool:
    head = text.lower()
    return head.startswith(("error", "usage:", "unknown")) or "unknown command" in head


def cmd_list(argv: list[str]) -> int:
    pretty = False
    for a in argv:
        if a in ("--pretty", "-p"):
            pretty = True
        else:
            sys.stderr.write(f"unknown flag: {a}\n")
            return 2
    rows = []
    for name in CONSUMERS:
        path = _which(name)
        rows.append({
            "tool": name,
            "installed": path is not None,
            "path": path,
            "version": _version_of(name) if path else None,
        })
    if pretty:
        sys.stdout.write(_format_list_pretty(rows))
        sys.stdout.write("\n")
    else:
        json.dump(rows, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    return 0


def _format_list_pretty(rows: list[dict]) -> str:
    name_w = max((len(r["tool"]) for r in rows), default=4)
    version_w = max((len(r["version"] or "-") for r in rows), default=7)
    name_w = max(name_w, len("tool"))
    version_w = max(version_w, len("version"))
    state_w = len("missing")

    def _line(tool, state, version, path):
        return "  ".join((
            tool.ljust(name_w),
            state.ljust(state_w),
            version.ljust(version_w),
            path,
        )).rstrip()

    out = [_line("tool", "state", "version", "path")]
    for r in rows:
        out.append(_line(
            r["tool"],
            "ok" if r["installed"] else "missing",
            r["version"] or "-",
            r["path"] or "-",
        ))
    return "\n".join(out)


def cmd_version(argv: list[str]) -> int:
    del argv
    sys.stdout.write(f"owa {__version__}\n")
    return 0


def cmd_doctor(argv: list[str]) -> int:
    path = _which("owa-doctor")
    if path is None:
        sys.stderr.write("owa-doctor not on PATH\n")
        return 13
    return subprocess.call([path, "probe", *argv])


def cmd_schema(argv: list[str]) -> int:
    """Aggregate `<tool> schema` output across installed consumers.

    Each consumer either ships a JSON schema (Phase 3+) or doesn't.
    Tools that don't yet support `schema` get a stub entry with
    ``"schema_supported": false``. With ``--tool <name>``, fetches a
    single tool only.
    """
    only = None
    if argv and argv[0] in ("--tool", "-t"):
        if len(argv) < 2:
            sys.stderr.write("--tool requires a value\n")
            return 2
        only = argv[1]
    aggregate = []
    for name in CONSUMERS:
        if only and name != only:
            continue
        path = _which(name)
        if path is None:
            aggregate.append({"tool": name, "installed": False})
            continue
        entry: dict[str, object] = {"tool": name, "installed": True, "path": path}
        try:
            proc = subprocess.run(
                [path, "schema"], capture_output=True, text=True, timeout=5,
            )
        except (subprocess.TimeoutExpired, OSError) as e:
            entry["schema_supported"] = False
            entry["error"] = str(e)
            aggregate.append(entry)
            continue
        if proc.returncode == 0 and proc.stdout.strip():
            try:
                entry["schema"] = json.loads(proc.stdout)
                entry["schema_supported"] = True
            except json.JSONDecodeError:
                entry["schema_supported"] = False
                entry["error"] = "non-JSON output from `schema`"
        else:
            entry["schema_supported"] = False
        aggregate.append(entry)
    json.dump(aggregate, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


def cmd_help(argv: list[str]) -> int:
    del argv
    sys.stdout.write(__doc__ or "")
    return 0


COMMANDS = {
    "list": cmd_list,
    "version": cmd_version,
    "doctor": cmd_doctor,
    "schema": cmd_schema,
    "help": cmd_help,
    "--help": cmd_help,
    "-h": cmd_help,
    "--version": cmd_version,
}


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # Top-level --doctor per hugr CONVENTIONS.md. The `owa doctor`
    # subcommand stays for back-compat (delegates to owa-doctor binary);
    # the flag form is the contract surface hugr doctor depends on.
    if is_doctor_invocation(argv):
        from owa_core.conventions import emit_doctor
        return emit_doctor("owa", "--json" in argv)
    if not argv:
        return cmd_help([])
    cmd = argv[0]
    handler = COMMANDS.get(cmd)
    if handler is None:
        sys.stderr.write(f"unknown command: {cmd}\n")
        return 2
    return handler(argv[1:])


if __name__ == "__main__":
    sys.exit(main())
