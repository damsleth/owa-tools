#!/usr/bin/env python3
"""Capture command-surface snapshots for owa-* consumer CLIs.

Phase 0 deliverable. The output format is **frozen at the start of Phase 0**;
changes to this script's fixture format require regenerating every fixture in
their own PR (see COMPAT.md).

What gets captured per (tool, command):

  * tool          - binary name, e.g. "owa-cal"
  * tool_version  - parsed from `<tool> --version` (best effort)
  * command       - subcommand name, e.g. "events", or "" for top-level
  * help_text     - stdout of `<tool> [command] --help`, scrubbed
  * help_exit     - exit code of the help invocation
  * subcommands   - list of subcommand names parsed from top-level help
  * flags         - list of flags parsed from the help text (best effort)
  * sample_json   - shape signature of a representative read invocation,
                    if one is configured for this command (paths + types,
                    no values). Empty if no sample probe exists.
  * exit_code     - exit code of the sample probe (paired with sample_json)
  * destructive   - true if the command is documented as destructive
                    (delete, rm, send, etc.)

Output: one JSON file per (tool, command) under
  tests/compat/fixtures/<tool>/<command-or-_root>.json

with a stable schema_version field at the top level for forward-compat.

Sample probes are intentionally read-only and idempotent. Capture defaults
to "help only" mode unless --probe-samples is passed, because not every
machine running this script has a working owa-piggy profile.

Scrubbing rules (applied to help_text and shape leaves):
  * email addresses -> "user@example.invalid"
  * GUIDs           -> "00000000-0000-0000-0000-000000000000"
  * absolute paths  -> "/REDACTED"
  * bearer tokens   -> "REDACTED"

Exit codes (this script):
  0  fixtures captured successfully
  1  one or more probes failed irrecoverably
  2  usage error
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_ROOT = REPO_ROOT / "tests" / "compat" / "fixtures"

SCHEMA_VERSION = 1

# The seven consumers. owa-piggy is intentionally not snapshotted here; it
# lives in its own repo and has its own contract.
TOOLS = (
    "owa-cal",
    "owa-mail",
    "owa-graph",
    "owa-doctor",
    "owa-people",
    "owa-sched",
    "owa-drive",
)

TOOL_MODULES = {
    "owa-cal": "owa_cal",
    "owa-mail": "owa_mail",
    "owa-graph": "owa_graph",
    "owa-doctor": "owa_doctor",
    "owa-people": "owa_people",
    "owa-sched": "owa_sched",
    "owa-drive": "owa_drive",
}

# Per-tool curated subcommand lists. Used when a tool's --help format does not
# match the generic parser (e.g., owa-graph's verb-first dispatch). These
# entries are the source of truth for fixture capture; the parser output is
# merged with this set. Keep them sorted; update with the changelog when a
# subcommand is added or removed.
KNOWN_SUBCOMMANDS: dict[str, tuple[str, ...]] = {
    "owa-cal": ("categories", "config", "create", "delete", "events", "help", "profiles", "refresh", "update"),
    "owa-mail": ("config", "delete", "folders", "forward", "help", "mark", "messages", "move", "refresh", "reply", "reply-all", "send", "show"),
    "owa-graph": (
        "DELETE", "GET", "PATCH", "POST", "PUT", "batch", "calendar",
        "chats", "config", "contacts", "directory", "files", "groups",
        "help", "mail", "me", "planner", "presence", "refresh", "sites",
        "teams", "todo", "users",
    ),
    "owa-doctor": ("probe",),
    "owa-people": ("config", "contacts", "directory", "find", "me", "refresh", "show"),
    "owa-sched": ("availability", "config", "find-time", "refresh"),
    "owa-drive": ("config", "get", "ls", "put", "refresh", "rm", "show"),
}

# Read-only probes. Only invoked when --probe-samples is passed AND
# stdout is captured cleanly. Designed to be idempotent and safe.
SAMPLE_PROBES: dict[str, list[tuple[str, list[str]]]] = {
    "owa-cal": [
        ("events", ["events", "--limit", "1"]),
        ("categories", ["categories"]),
    ],
    "owa-mail": [
        ("folders", ["folders"]),
        ("messages", ["messages", "--limit", "1"]),
    ],
    "owa-graph": [
        ("get_me", ["GET", "/me"]),
    ],
    "owa-doctor": [
        ("probe", ["probe", "--no-tokens"]),
    ],
    "owa-people": [
        ("me", ["me"]),
    ],
    "owa-sched": [
        # No safe zero-arg probe; intentionally empty.
    ],
    "owa-drive": [
        ("ls_root", ["ls", "/"]),
    ],
}

# Commands whose semantics are destructive. Tracked so the contract tests
# can assert non-TTY refusal behavior later.
DESTRUCTIVE_COMMANDS: dict[str, set[str]] = {
    "owa-cal": {"delete"},
    "owa-mail": {"delete", "send", "reply", "reply-all", "forward", "move", "mark"},
    "owa-graph": {"DELETE", "POST", "PATCH", "PUT", "batch"},
    "owa-drive": {"rm", "put"},
}


# Scrubbing -----------------------------------------------------------------

EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
GUID_RE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)
HOMEDIR = os.path.expanduser("~")
BEARER_RE = re.compile(r"Bearer\s+[A-Za-z0-9_\-.~+/=]{20,}")


def scrub(text: str) -> str:
    if not text:
        return text
    text = EMAIL_RE.sub("user@example.invalid", text)
    text = GUID_RE.sub("00000000-0000-0000-0000-000000000000", text)
    text = BEARER_RE.sub("Bearer REDACTED", text)
    if HOMEDIR:
        text = text.replace(HOMEDIR, "/REDACTED")
    return text


# Shape extraction ----------------------------------------------------------

def shape_of(value: Any, *, depth: int = 0, max_depth: int = 6) -> Any:
    """Reduce a JSON value to its type signature, recursively.

    For dicts: {key: shape_of(value)}.
    For lists: ["<element-shape>"] using the first item, or [] if empty.
    For scalars: type name as a string ("str", "int", "bool", "null").
    """
    if depth > max_depth:
        return "<truncated>"
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    if isinstance(value, list):
        if not value:
            return []
        return [shape_of(value[0], depth=depth + 1, max_depth=max_depth)]
    if isinstance(value, dict):
        return {
            k: shape_of(v, depth=depth + 1, max_depth=max_depth)
            for k, v in sorted(value.items())
        }
    return f"<{type(value).__name__}>"


# Help-text parsing ---------------------------------------------------------

SUBCMD_HEADER_RE = re.compile(r"^(commands|subcommands|usage):", re.I)
FLAG_RE = re.compile(r"--[a-z][a-z0-9-]*", re.I)


def parse_subcommands(help_text: str) -> list[str]:
    """Best-effort subcommand extraction from --help text.

    Each tool has its own help format; this collects tokens that look like
    subcommand names and reports them sorted and de-duplicated. The
    compatibility test only asserts presence of known names, not order.
    """
    found: set[str] = set()
    in_block = False
    for line in help_text.splitlines():
        stripped = line.strip()
        if not stripped:
            in_block = False
            continue
        if SUBCMD_HEADER_RE.match(stripped):
            in_block = True
            continue
        if in_block:
            # Lines that begin with a word followed by 2+ spaces look like
            # "subcmd     description" entries.
            m = re.match(r"^([a-z][a-z0-9-]*)\s{2,}", stripped)
            if m:
                found.add(m.group(1))
    return sorted(found)


def parse_flags(help_text: str) -> list[str]:
    return sorted(set(FLAG_RE.findall(help_text)))


# Subprocess helpers --------------------------------------------------------

def _argv_for(binary: str, args: list[str]) -> list[str] | None:
    module = TOOL_MODULES.get(binary)
    if module:
        return [sys.executable, "-m", module, *args]
    path = shutil.which(binary)
    if path is not None:
        return [path, *args]
    return None


def run(binary: str, args: list[str], *, timeout: float = 10.0) -> tuple[int, str, str]:
    argv = _argv_for(binary, args)
    if argv is None:
        return -1, "", f"{binary}: not found on PATH"
    try:
        out = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return -1, "", f"{binary} {args}: timeout"
    return out.returncode, out.stdout or "", out.stderr or ""


def tool_version(binary: str) -> str:
    """Best-effort version extraction. Tries `--version` first; falls back to
    the first line of `--help`. Returns "" if the binary isn't installed."""
    rc, stdout, stderr = run(binary, ["--version"], timeout=5)
    if rc < 0:
        return ""
    text = (stdout or stderr).strip()
    # Some tools (owa-graph) don't accept --version; reject obvious error
    # strings and fall through to help-line extraction.
    if text and not _looks_like_error(text):
        return scrub(text.splitlines()[0])
    rc2, stdout2, _ = run(binary, ["--help"], timeout=5)
    if rc2 < 0:
        return ""
    head = (stdout2 or "").strip().splitlines()[:1]
    return scrub(head[0]) if head else ""


def _looks_like_error(text: str) -> bool:
    head = text.strip().lower()
    return head.startswith(("error", "usage:", "unknown")) or "unknown command" in head


# Capture core --------------------------------------------------------------

def capture_help(binary: str, command: str | None) -> dict[str, Any]:
    args = (["--help"] if command is None else [command, "--help"])
    rc, stdout, stderr = run(binary, args)
    text = scrub(stdout if stdout else stderr)
    return {
        "help_text": text,
        "help_exit": rc,
        "subcommands": parse_subcommands(text) if command is None else [],
        "flags": parse_flags(text),
    }


def capture_sample(binary: str, args: list[str]) -> dict[str, Any]:
    result = run(binary, args, timeout=20)
    rc = result[0]
    stdout = result[1]
    sample: dict[str, Any] = {
        "exit_code": rc,
        "sample_json": None,
    }
    if rc == 0 and stdout.strip():
        try:
            value = json.loads(stdout)
        except json.JSONDecodeError:
            sample["sample_json"] = "<not-json>"
        else:
            sample["sample_json"] = shape_of(value)
    return sample


def fixture_path(tool: str, command: str | None) -> Path:
    name = command or "_root"
    return FIXTURE_ROOT / tool / f"{name}.json"


def write_fixture(tool: str, command: str | None, payload: dict[str, Any]) -> Path:
    path = fixture_path(tool, command)
    path.parent.mkdir(parents=True, exist_ok=True)
    full = {
        "schema_version": SCHEMA_VERSION,
        "tool": tool,
        "command": command or "",
        **payload,
    }
    text = json.dumps(full, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path.write_text(text, encoding="utf-8")
    return path


def snapshot_tool(tool: str, *, probe_samples: bool) -> list[Path]:
    """Capture every fixture for one tool. Returns the list of files written."""
    written: list[Path] = []

    if _argv_for(tool, []) is None:
        # Mark not-installed cleanly. Re-run after pipx/brew install.
        write_fixture(tool, None, {
            "tool_version": "",
            "installed": False,
            "help_text": "",
            "help_exit": -1,
            "subcommands": list(KNOWN_SUBCOMMANDS.get(tool, ())),
            "flags": [],
            "destructive": False,
            "sample_json": None,
            "exit_code": None,
        })
        written.append(fixture_path(tool, None))
        return written

    # Top-level help.
    base = capture_help(tool, command=None)
    base["tool_version"] = tool_version(tool)
    base["installed"] = True
    base["destructive"] = False
    base["sample_json"] = None
    base["exit_code"] = None
    # Merge parsed subcommands with the curated list. Curation is the source
    # of truth; the parser is a cross-check that surfaces drift.
    parsed = set(base["subcommands"])
    curated = set(KNOWN_SUBCOMMANDS.get(tool, ()))
    base["subcommands"] = sorted(parsed | curated)
    base["subcommands_parsed"] = sorted(parsed)
    base["subcommands_curated"] = sorted(curated)
    written.append(write_fixture(tool, None, base))

    # Per-subcommand help.
    seen: set[str] = parsed | curated
    for command in sorted(seen):
        cmd_payload = capture_help(tool, command=command)
        cmd_payload["tool_version"] = base["tool_version"]
        cmd_payload["destructive"] = command in DESTRUCTIVE_COMMANDS.get(tool, set())
        cmd_payload["sample_json"] = None
        cmd_payload["exit_code"] = None
        written.append(write_fixture(tool, command, cmd_payload))

    # Optional read-only sample probes.
    if probe_samples:
        for label, args in SAMPLE_PROBES.get(tool, []):
            sample = capture_sample(tool, args)
            target = fixture_path(tool, f"sample_{label}")
            target.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "schema_version": SCHEMA_VERSION,
                "tool": tool,
                "command": label,
                "tool_version": tool_version(tool),
                "invocation": args,
                **sample,
            }
            target.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            written.append(target)

    return written


# CLI -----------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Capture compat fixtures for owa-* CLIs")
    parser.add_argument(
        "--tool",
        action="append",
        default=None,
        help="Tool name (repeatable). Defaults to all seven consumers.",
    )
    parser.add_argument(
        "--probe-samples",
        action="store_true",
        help="Run read-only sample probes. Requires owa-piggy and a working profile.",
    )
    parser.add_argument(
        "--scrub-only",
        metavar="TEXT",
        help="Print scrubbed version of TEXT and exit. For debugging the scrubber.",
    )
    args = parser.parse_args()

    if args.scrub_only is not None:
        sys.stdout.write(scrub(args.scrub_only) + "\n")
        return 0

    targets = args.tool or list(TOOLS)
    bad = [t for t in targets if t not in TOOLS]
    if bad:
        sys.stderr.write(f"unknown tools: {', '.join(bad)}\n")
        return 2

    failures = 0
    for tool in targets:
        try:
            written = snapshot_tool(tool, probe_samples=args.probe_samples)
        except Exception as exc:  # noqa: BLE001
            sys.stderr.write(f"{tool}: capture failed: {exc}\n")
            failures += 1
            continue
        for path in written:
            sys.stdout.write(f"wrote {path.relative_to(REPO_ROOT)}\n")

    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
