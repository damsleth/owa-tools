#!/usr/bin/env python3
"""Stdlib-only import checker for owa-tools runtime code.

Walks the Python source under each runtime package, parses imports via the
`ast` module, and flags any module that imports a non-stdlib package outside
the suite allowlist.

Allowed at runtime:
  * Python stdlib (resolved via sys.stdlib_module_names on 3.10+;
    bundled allowlist on 3.9).
  * Local suite packages: owa_core, owa_cal, owa_mail, owa_graph,
    owa_doctor, owa_people, owa_sched, owa_drive, owa_todo, owa.
  * Sanctioned runtime dependencies declared in pyproject.toml
    [project].dependencies (see RUNTIME_DEPS below): currently none -
    the suite is stdlib-only.
  * `owa-piggy` is invoked via subprocess only; no Python import.

Excluded from the check:
  * tests/ directories.
  * tools/ directories (this script and its siblings).
  * any path component named `tests`.

Exit codes:
  0  clean
  1  one or more disallowed imports found
  2  internal error (couldn't read a file)

This script must itself be stdlib-only.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"

LOCAL_PACKAGES = frozenset({
    "owa",
    "owa_core",
    "owa_cal",
    "owa_mail",
    "owa_graph",
    "owa_doctor",
    "owa_people",
    "owa_sched",
    "owa_drive",
    "owa_todo",
    "owa_planner",
    "owa_sites",
    "owa_teams",
    "owa_vids",
})

# Third-party runtime dependencies the suite is allowed to import. Must
# stay in sync with pyproject.toml [project].dependencies. The suite is
# stdlib-only, so this is empty; add an entry here only alongside a real
# dependency in pyproject.toml.
RUNTIME_DEPS: frozenset[str] = frozenset()

# Bundled stdlib list for Python 3.9 (sys.stdlib_module_names is 3.10+).
# Source: Python 3.9 docs index of standard library modules.
STDLIB_FALLBACK = frozenset({
    "__future__", "_thread", "abc", "aifc", "argparse", "array", "ast",
    "asynchat", "asyncio", "asyncore", "atexit", "audioop", "base64",
    "bdb", "binascii", "bisect", "builtins", "bz2", "calendar", "cgi",
    "cgitb", "chunk", "cmath", "cmd", "code", "codecs", "codeop",
    "collections", "colorsys", "compileall", "concurrent", "configparser",
    "contextlib", "contextvars", "copy", "copyreg", "cProfile", "crypt",
    "csv", "ctypes", "curses", "dataclasses", "datetime", "dbm", "decimal",
    "difflib", "dis", "distutils", "doctest", "email", "encodings",
    "ensurepip", "enum", "errno", "faulthandler", "fcntl", "filecmp",
    "fileinput", "fnmatch", "fractions", "ftplib", "functools", "gc",
    "genericpath", "getopt", "getpass", "gettext", "glob", "graphlib",
    "grp", "gzip", "hashlib", "heapq", "hmac", "html", "http", "idlelib",
    "imaplib", "imghdr", "imp", "importlib", "inspect", "io", "ipaddress",
    "itertools", "json", "keyword", "lib2to3", "linecache", "locale",
    "logging", "lzma", "mailbox", "mailcap", "marshal", "math", "mimetypes",
    "mmap", "modulefinder", "msilib", "msvcrt", "multiprocessing",
    "netrc", "nis", "nntplib", "ntpath", "numbers", "opcode", "operator",
    "optparse", "os", "ossaudiodev", "parser", "pathlib", "pdb", "pickle",
    "pickletools", "pipes", "pkgutil", "platform", "plistlib", "poplib",
    "posix", "posixpath", "pprint", "profile", "pstats", "pty", "pwd",
    "py_compile", "pyclbr", "pydoc", "pydoc_data", "pyexpat", "queue",
    "quopri", "random", "re", "readline", "reprlib", "resource", "rlcompleter",
    "runpy", "sched", "secrets", "select", "selectors", "shelve", "shlex",
    "shutil", "signal", "site", "smtpd", "smtplib", "sndhdr", "socket",
    "socketserver", "spwd", "sqlite3", "sre_compile", "sre_constants",
    "sre_parse", "ssl", "stat", "statistics", "string", "stringprep",
    "struct", "subprocess", "sunau", "symbol", "symtable", "sys",
    "sysconfig", "syslog", "tabnanny", "tarfile", "telnetlib", "tempfile",
    "termios", "test", "textwrap", "threading", "time", "timeit", "tkinter",
    "token", "tokenize", "trace", "traceback", "tracemalloc", "tty",
    "turtle", "turtledemo", "types", "typing", "unicodedata", "unittest",
    "urllib", "uu", "uuid", "venv", "warnings", "wave", "weakref",
    "webbrowser", "winreg", "winsound", "wsgiref", "xdrlib", "xml", "xmlrpc",
    "zipapp", "zipfile", "zipimport", "zlib", "zoneinfo",
})


def stdlib_names() -> frozenset[str]:
    names = getattr(sys, "stdlib_module_names", None)
    if names is None:
        return STDLIB_FALLBACK
    return frozenset(names) | STDLIB_FALLBACK


def is_excluded(path: Path) -> bool:
    parts = set(path.parts)
    if "tests" in parts:
        return True
    if "tools" in parts:
        return True
    if "__pycache__" in parts:
        return True
    return False


def runtime_python_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for pkg in LOCAL_PACKAGES:
        pkg_root = root / pkg
        if not pkg_root.exists():
            continue
        for path in pkg_root.rglob("*.py"):
            if is_excluded(path.relative_to(root)):
                continue
            files.append(path)
    return files


def top_level(name: str) -> str:
    return name.split(".", 1)[0]


def disallowed_imports(file: Path, allowed: frozenset[str]) -> list[tuple[int, str]]:
    src = file.read_text(encoding="utf-8")
    try:
        tree = ast.parse(src, filename=str(file))
    except SyntaxError as exc:
        raise SystemExit(f"syntax error in {file}: {exc}") from exc
    bad: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = top_level(alias.name)
                if root and root not in allowed:
                    bad.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom):
            # Relative imports (from . import ...) have module=None or empty.
            if node.level and not node.module:
                continue
            if node.level:
                # Relative; resolves within the local package, OK.
                continue
            module = node.module or ""
            root = top_level(module)
            if root and root not in allowed:
                bad.append((node.lineno, module))
    return bad


def main() -> int:
    allowed = stdlib_names() | LOCAL_PACKAGES | RUNTIME_DEPS
    failures: list[tuple[Path, int, str]] = []
    for file in runtime_python_files(SRC_ROOT):
        try:
            for lineno, name in disallowed_imports(file, allowed):
                failures.append((file, lineno, name))
        except OSError as exc:
            sys.stderr.write(f"could not read {file}: {exc}\n")
            return 2

    if not failures:
        sys.stdout.write("stdlib-only check: OK\n")
        return 0

    sys.stderr.write("stdlib-only check: FAIL\n")
    for file, lineno, name in failures:
        rel = file.relative_to(REPO_ROOT)
        sys.stderr.write(f"  {rel}:{lineno}: imports '{name}' (not in allowlist)\n")
    sys.stderr.write(
        "\nAllowlist: Python stdlib + "
        + ", ".join(sorted(LOCAL_PACKAGES | RUNTIME_DEPS))
        + "\n"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
