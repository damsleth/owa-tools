"""Tests for owa_core.tui_kit.settings — generic cycle/persist engine.

Uses a sample dataclass to prove the engine is dataclass-agnostic.
"""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from owa_core.tui_kit import settings as kit

PANES = ('right', 'bottom', 'off')
RATIOS = (40, 50, 60)


@dataclass(frozen=True)
class Sample:
    pane: str = 'right'
    ratio: int = 50
    note: str = ''


DEFAULTS = Sample()
ALLOWED = {'pane': PANES, 'ratio': RATIOS}
FREE_TEXT = frozenset({'note'})
FIELD_TO_KEY = {'pane': 'k_pane', 'ratio': 'k_ratio', 'note': 'k_note'}
COERCERS = {'ratio': int}


def _cycle(s, field):
    return kit.cycle(s, field, allowed=ALLOWED, free_text=FREE_TEXT)


def _from(config):
    return kit.from_config(config, defaults=DEFAULTS, field_to_key=FIELD_TO_KEY,
                           allowed=ALLOWED, free_text=FREE_TEXT, coercers=COERCERS)


class TestCycle:
    def test_advances(self):
        assert _cycle(Sample(pane='right'), 'pane').pane == 'bottom'

    def test_wraps(self):
        assert _cycle(Sample(pane='off'), 'pane').pane == 'right'

    def test_invalid_current_jumps_to_first(self):
        assert _cycle(Sample(pane='bogus'), 'pane').pane == 'right'

    def test_free_text_is_noop(self):
        s = Sample(note='x')
        assert _cycle(s, 'note') is s

    def test_unknown_field_raises(self):
        with pytest.raises(ValueError):
            _cycle(Sample(), 'nope')

    def test_does_not_mutate(self):
        s = Sample(pane='right')
        _cycle(s, 'pane')
        assert s.pane == 'right'


class TestFromConfig:
    def test_absent_uses_default(self):
        assert _from({}) == DEFAULTS

    def test_coerced_int(self):
        s = _from({'k_ratio': '40'})
        assert s.ratio == 40 and isinstance(s.ratio, int)

    def test_coerce_failure_falls_back(self):
        assert _from({'k_ratio': 'half'}).ratio == 50

    def test_coerced_out_of_range_falls_back(self):
        assert _from({'k_ratio': '99'}).ratio == 50

    def test_enum_invalid_falls_back(self):
        assert _from({'k_pane': 'sideways'}).pane == 'right'

    def test_enum_valid(self):
        assert _from({'k_pane': 'off'}).pane == 'off'

    def test_free_text_any_string(self):
        assert _from({'k_note': '%Y'}).note == '%Y'

    def test_field_without_allowed_passes_through(self):
        # 'extra' has a key but no allowed/coercer/free-text entry -> raw kept
        @dataclass(frozen=True)
        class S2:
            extra: str = 'd'
        out = kit.from_config({'k': 'raw'}, defaults=S2(),
                              field_to_key={'extra': 'k'}, allowed={})
        assert out.extra == 'raw'


class TestToConfigDict:
    def test_serialises_to_strings(self):
        out = kit.to_config_dict(Sample(pane='off', ratio=60, note='n'),
                                 field_to_key=FIELD_TO_KEY)
        assert out == {'k_pane': 'off', 'k_ratio': '60', 'k_note': 'n'}

    def test_roundtrip(self):
        s = Sample(pane='bottom', ratio=40, note='x')
        assert _from(kit.to_config_dict(s, field_to_key=FIELD_TO_KEY)) == s
