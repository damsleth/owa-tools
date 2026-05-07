"""Atomic key-value config files with per-tool allowlists.

Format: key=value lines, mode 0600, atomic temp+fsync+rename writes.
Comments (#-prefixed) and blank lines are preserved on read but not
re-emitted on write.

Public surface:
    Config(path, allowed_keys)
        .get(key) -> str | None
        .set(key, value) -> None
        .delete(key) -> None
        .save_atomic() -> None
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Iterable

from .errors import UsageError


class Config:
    def __init__(self, path: Path | str, allowed_keys: Iterable[str]) -> None:
        self.path = Path(path)
        self.allowed_keys = frozenset(allowed_keys)
        self._values: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        for raw in self.path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            if key in self.allowed_keys:
                self._values[key] = value.strip()

    def _check_key(self, key: str) -> None:
        if key not in self.allowed_keys:
            raise UsageError(
                f"unknown config key: {key}",
                hint=f"allowed: {', '.join(sorted(self.allowed_keys))}",
            )

    def get(self, key: str) -> str | None:
        self._check_key(key)
        return self._values.get(key)

    def set(self, key: str, value: str) -> None:
        self._check_key(key)
        self._values[key] = value

    def delete(self, key: str) -> None:
        self._check_key(key)
        self._values.pop(key, None)

    def items(self) -> list[tuple[str, str]]:
        return sorted(self._values.items())

    def save_atomic(self) -> None:
        """Write to a temp file in the same directory, fsync, then rename.

        File mode is 0600; the parent directory is created if missing.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        body = "".join(f"{k}={v}\n" for k, v in sorted(self._values.items()))
        fd, tmp_path = tempfile.mkstemp(
            prefix=".{}.".format(self.path.name),
            dir=str(self.path.parent),
        )
        try:
            os.write(fd, body.encode("utf-8"))
            os.fsync(fd)
            os.close(fd)
            os.chmod(tmp_path, 0o600)
            os.replace(tmp_path, self.path)
        except Exception:
            try:
                os.close(fd)
            except OSError:
                pass
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
