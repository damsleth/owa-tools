"""Compatibility snapshot replay.

These tests make the Phase 0 fixtures active: help surface, flags,
subcommand inventory, and selected exit codes now fail in CI when they
drift unintentionally.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools import snapshot_cli


FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures"


def _fixture_paths() -> list[Path]:
    return sorted(p for p in FIXTURE_ROOT.rglob("*.json") if not p.name.startswith("sample_"))


@pytest.mark.parametrize("path", _fixture_paths(), ids=lambda p: str(p.relative_to(FIXTURE_ROOT)))
def test_help_snapshot(path: Path):
    fixture = json.loads(path.read_text(encoding="utf-8"))
    tool = fixture["tool"]
    command = fixture["command"] or None

    if command is None:
        assert fixture.get("installed") is True

    captured = snapshot_cli.capture_help(tool, command=command)
    assert captured["help_exit"] == fixture["help_exit"]
    assert captured["help_text"] == fixture["help_text"]
    assert captured["flags"] == fixture["flags"]
    if command is None:
        assert captured["subcommands"] == fixture["subcommands_parsed"]
