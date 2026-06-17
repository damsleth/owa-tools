"""Tests for owa-cal cmd_tui CLI integration.

Covers:
- cmd_tui refuses non-interactive (is_interactive() -> False)
- cmd_tui refuses under --agent (interactive_commands gate in modes.py)
- schema lists tui with interactive=True
- unknown flag -> UsageError
- tui dispatched correctly when interactive + auth succeeds
"""
from __future__ import annotations

import pytest

from owa_cal.cli import (
    COMMAND_SCHEMA,
    cmd_tui,
    main,
)
from owa_core.errors import UsageError

# ---------------------------------------------------------------------------
# Schema assertions
# ---------------------------------------------------------------------------

class TestTuiSchema:
    def _tui_entry(self):
        return next((c for c in COMMAND_SCHEMA if c['name'] == 'tui'), None)

    def test_tui_in_schema(self):
        entry = self._tui_entry()
        assert entry is not None

    def test_tui_marked_interactive(self):
        entry = self._tui_entry()
        assert entry.get('interactive') is True

    def test_tui_auth_outlook(self):
        entry = self._tui_entry()
        assert entry.get('auth', {}).get('audience') == 'outlook'

    def test_tui_has_day_range_flag(self):
        entry = self._tui_entry()
        flags = [f['name'] for f in entry.get('flags', [])]
        assert '--day-range' in flags


# ---------------------------------------------------------------------------
# cmd_tui refuses non-interactive
# ---------------------------------------------------------------------------

class TestCmdTuiRefusesNonInteractive:
    def test_raises_usage_error_non_interactive(self, monkeypatch):
        import owa_core.tty as tty_mod
        monkeypatch.setattr(tty_mod, 'is_interactive', lambda: False)
        with pytest.raises(UsageError, match='interactive terminal'):
            cmd_tui([], {}, 'tok', 'https://example.com')

    def test_unknown_flag_raises_usage_error(self, monkeypatch):
        import owa_core.tty as tty_mod
        monkeypatch.setattr(tty_mod, 'is_interactive', lambda: True)
        with pytest.raises(UsageError, match='Unknown flag'):
            cmd_tui(['--bogus-flag'], {}, 'tok', 'https://example.com')

    def test_day_range_accepted(self, monkeypatch):
        """--day-range is a valid flag; proceeds to tui.run (mocked)."""
        import owa_core.tty as tty_mod
        monkeypatch.setattr(tty_mod, 'is_interactive', lambda: True)
        import owa_cal.tui as tui_mod
        monkeypatch.setattr(tui_mod, 'run', lambda *a, **kw: 0)
        rc = cmd_tui(['--day-range', 'week'], {}, 'tok', 'https://example.com')
        assert rc == 0


# ---------------------------------------------------------------------------
# Agent mode refusal via main()
# ---------------------------------------------------------------------------

class TestAgentModeRefusal:
    def test_agent_flag_refuses_tui(self, monkeypatch):
        """--agent + tui should return a non-zero exit code with an error."""
        import owa_core.tty as tty_mod
        monkeypatch.setattr(tty_mod, 'is_interactive', lambda: False)
        # --agent is stripped by run_with_output_modes; it gates tui out
        rc = main(['--agent', 'tui'])
        assert rc != 0

    def test_agent_env_refuses_tui(self, monkeypatch):
        """OWA_AGENT=1 + tui should also be refused."""
        import owa_core.tty as tty_mod
        monkeypatch.setattr(tty_mod, 'is_interactive', lambda: False)
        monkeypatch.setenv('OWA_AGENT', '1')
        rc = main(['tui'])
        assert rc != 0
        monkeypatch.delenv('OWA_AGENT', raising=False)


# ---------------------------------------------------------------------------
# Dispatch: tui reaches tui.run when interactive + auth OK
# ---------------------------------------------------------------------------

class TestDispatchToTuiRun:
    def test_tui_dispatched_when_interactive(self, monkeypatch, tmp_config):
        """cmd_tui calls tui.run() when is_interactive() is True and auth OK."""
        import owa_cal.auth as auth_mod
        import owa_cal.tui as tui_mod
        import owa_core.tty as tty_mod

        monkeypatch.setattr(tty_mod, 'is_interactive', lambda: True)
        monkeypatch.setattr(
            auth_mod, 'setup_auth',
            lambda config, debug=False: ('fake_token', 'https://example.com'),
        )
        run_calls = []
        monkeypatch.setattr(
            tui_mod, 'run',
            lambda config, token, api_base, **kw: run_calls.append(True) or 0,
        )

        from owa_cal.cli import _main
        rc = _main(['tui'])
        assert rc == 0
        assert run_calls == [True]
