"""Tests for cli.build_report and exit-code policy."""
import json
import shutil
import subprocess

import pytest

from owa_core.registry import CONSUMER_TOOLS
from owa_doctor import cli as cli_mod
from owa_doctor import probe as probe_mod

# Canonical schema for a siblings[] entry returned by probe_siblings() /
# build_report(). Keys that must be present and their expected types.
_SIBLING_ENTRY_SCHEMA = {
  'name': str,
  'installed': bool,
  'version': (str, type(None)),
  'path': (str, type(None)),
}

# Canonical schema for a per-binary `<binary> --doctor --json` payload.
# Sourced from real payloads (see contract/test_doctor_flag.py).
_DOCTOR_PAYLOAD_SCHEMA = {
  'tool': str,
  'version': str,
  'findings': list,
}


def test_build_report_no_piggy(monkeypatch):
    monkeypatch.setattr(probe_mod, 'probe_piggy', lambda **kw: {
        'installed': False, 'reachable': False, 'version': None, 'path': None,
    })
    monkeypatch.setattr(probe_mod, 'probe_siblings', lambda **kw: [])
    report = cli_mod.build_report()
    assert report['summary']['fail'] == 1
    assert cli_mod._exit_code_for(report) == 2


def test_build_report_all_ok(monkeypatch):
    monkeypatch.setattr(probe_mod, 'probe_piggy', lambda **kw: {
        'installed': True, 'reachable': True, 'version': '0.7.1', 'path': '/x',
    })
    monkeypatch.setattr(probe_mod, 'probe_siblings', lambda **kw: [])
    monkeypatch.setattr(probe_mod, 'list_piggy_profiles',
                        lambda: (['swon'], 'swon'))
    monkeypatch.setattr(probe_mod, 'probe_profile_token', lambda alias, audience='graph': {
        'alias': alias, 'audience': audience,
        'token_ok': True, 'minutes_remaining': 60,
        'token_audience': 'graph', 'audience_mismatch': False, 'error': None,
    })
    report = cli_mod.build_report()
    assert report['summary'] == {'ok': 1, 'warn': 0, 'fail': 0}
    assert cli_mod._exit_code_for(report) == 0


def test_build_report_warn(monkeypatch):
    monkeypatch.setattr(probe_mod, 'probe_piggy', lambda **kw: {
        'installed': True, 'reachable': True, 'version': '0.7.1', 'path': '/x',
    })
    monkeypatch.setattr(probe_mod, 'probe_siblings', lambda **kw: [])
    monkeypatch.setattr(probe_mod, 'list_piggy_profiles',
                        lambda: (['swon'], 'swon'))
    monkeypatch.setattr(probe_mod, 'probe_profile_token', lambda alias, audience='graph': {
        'alias': alias, 'audience': audience,
        'token_ok': True, 'minutes_remaining': 5,
        'token_audience': 'graph', 'audience_mismatch': False, 'error': None,
    })
    report = cli_mod.build_report()
    assert report['summary']['warn'] == 1
    assert cli_mod._exit_code_for(report) == 1


def test_build_report_no_tokens_skips_profile_probe(monkeypatch):
    called = {'n': 0}

    def fake_probe(alias, audience='graph', **kw):
        called['n'] += 1
        return {}

    monkeypatch.setattr(probe_mod, 'probe_piggy', lambda **kw: {
        'installed': True, 'reachable': True, 'version': '0.7.1', 'path': '/x',
    })
    monkeypatch.setattr(probe_mod, 'probe_siblings', lambda **kw: [])
    monkeypatch.setattr(probe_mod, 'probe_profile_token', fake_probe)
    monkeypatch.setattr(probe_mod, 'list_piggy_profiles',
                        lambda: (['swon'], 'swon'))
    report = cli_mod.build_report(no_tokens=True)
    assert called['n'] == 0
    assert report['profiles'] == []


def _assert_sibling_entry_schema(entry, label):
  """Assert that a siblings[] entry conforms to _SIBLING_ENTRY_SCHEMA."""
  for key, expected_type in _SIBLING_ENTRY_SCHEMA.items():
    assert key in entry, f'{label}: missing key {key!r}'
    assert isinstance(entry[key], expected_type), (
      f'{label}: key {key!r} has type {type(entry[key]).__name__!r}, '
      f'expected {expected_type}'
    )


def _assert_doctor_payload_schema(payload, label):
  """Assert that a --doctor --json payload conforms to _DOCTOR_PAYLOAD_SCHEMA."""
  for key, expected_type in _DOCTOR_PAYLOAD_SCHEMA.items():
    assert key in payload, f'{label}: missing key {key!r}'
    assert isinstance(payload[key], expected_type), (
      f'{label}: key {key!r} has type {type(payload[key]).__name__!r}, '
      f'expected {expected_type}'
    )


@pytest.mark.parametrize('binary', list(CONSUMER_TOOLS))
def test_siblings_match_per_binary_doctor(binary):
  """Cross-check: each siblings[] entry is schema-compatible with that
  binary's own `<binary> --doctor --json` payload, and the stable
  fields (tool name, version) agree between the two sides.

  Aggregate side: probe_siblings() (called directly - it is the exact
  function build_report() uses to populate siblings[]).
  Per-binary side: subprocess shell-out to the installed binary.

  Skipped when the binary is not on PATH so the test stays green in
  minimal CI environments.
  """
  if not shutil.which(binary):
    pytest.skip(f'{binary!r} not found on PATH')

  # --- aggregate side: get the entry build_report() would emit ---
  siblings = probe_mod.probe_siblings()
  agg_entry = next((s for s in siblings if s['name'] == binary), None)
  assert agg_entry is not None, (
    f'{binary!r} not in probe_siblings() output even though it is on PATH'
  )
  _assert_sibling_entry_schema(agg_entry, label=f'siblings[{binary!r}]')

  # --- per-binary side: run `<binary> --doctor --json` ---
  proc = subprocess.run(
    [binary, '--doctor', '--json'],
    capture_output=True, text=True, timeout=10,
  )
  assert proc.returncode in (0, 1), (
    f'{binary} --doctor --json exited {proc.returncode}; '
    f'stderr: {proc.stderr.strip()!r}'
  )
  try:
    payload = json.loads(proc.stdout.strip())
  except json.JSONDecodeError as exc:
    raise AssertionError(
      f'{binary} --doctor --json produced non-JSON stdout: '
      f'{proc.stdout.strip()!r}'
    ) from exc
  _assert_doctor_payload_schema(payload, label=f'{binary} --doctor --json')

  # --- cross-check: stable fields must agree across both sides ---
  # tool name in payload must equal the binary name
  assert payload['tool'] == binary, (
    f'{binary}: payload["tool"]={payload["tool"]!r} != binary name {binary!r}'
  )
  # version reported by the binary must equal what the aggregator recorded
  assert payload['version'] == agg_entry['version'], (
    f'{binary}: per-binary version={payload["version"]!r} '
    f'!= aggregated version={agg_entry["version"]!r}'
  )


def test_build_report_broker_unreachable(monkeypatch):
    """Broker installed but unreachable is fatal: fail summary, exit 2, no probes."""
    monkeypatch.setattr(probe_mod, 'probe_piggy', lambda **kw: {
        'installed': True, 'reachable': False, 'version': None, 'path': '/x',
    })
    monkeypatch.setattr(probe_mod, 'probe_siblings', lambda **kw: [])
    called = {'n': 0}
    monkeypatch.setattr(probe_mod, 'probe_profile_token',
                        lambda *a, **kw: called.__setitem__('n', called['n'] + 1) or {})
    monkeypatch.setattr(probe_mod, 'list_piggy_profiles', lambda: (['swon'], 'swon'))
    report = cli_mod.build_report()
    assert report['summary']['fail'] == 1
    assert report['profiles'] == []
    assert called['n'] == 0
    assert cli_mod._exit_code_for(report) == 2


def test_build_report_profile_subset(monkeypatch):
    monkeypatch.setattr(probe_mod, 'probe_piggy', lambda **kw: {
        'installed': True, 'reachable': True, 'version': '0.7.1', 'path': '/x',
    })
    monkeypatch.setattr(probe_mod, 'probe_siblings', lambda **kw: [])
    monkeypatch.setattr(probe_mod, 'list_piggy_profiles',
                        lambda: (['work', 'home', 'agent'], 'work'))
    monkeypatch.setattr(probe_mod, 'probe_profile_token', lambda alias, audience='graph', **kw: {
        'alias': alias, 'audience': audience, 'token_ok': True,
        'minutes_remaining': 60, 'token_audience': 'graph',
        'audience_mismatch': False, 'error': None,
    })
    report = cli_mod.build_report(profile_filter=['home', 'agent'])
    aliases = [p['alias'] for p in report['profiles']]
    assert aliases == ['home', 'agent']  # filtered, original order preserved


def test_build_report_unknown_in_subset(monkeypatch):
    monkeypatch.setattr(probe_mod, 'probe_piggy', lambda **kw: {
        'installed': True, 'reachable': True, 'version': '0.7.1', 'path': '/x',
    })
    monkeypatch.setattr(probe_mod, 'probe_siblings', lambda **kw: [])
    monkeypatch.setattr(probe_mod, 'list_piggy_profiles', lambda: (['work'], 'work'))
    with pytest.raises(cli_mod.UsageError, match='not found'):
        cli_mod.build_report(profile_filter=['work', 'nope'])


def test_build_report_coverage(monkeypatch):
    monkeypatch.setattr(probe_mod, 'probe_piggy', lambda **kw: {
        'installed': True, 'reachable': True, 'version': '0.7.1', 'path': '/x',
    })
    monkeypatch.setattr(probe_mod, 'probe_siblings', lambda **kw: [])
    monkeypatch.setattr(probe_mod, 'list_piggy_profiles', lambda: (['work'], 'work'))
    monkeypatch.setattr(probe_mod, 'probe_profile_token', lambda alias, audience='graph', **kw: {
        'alias': alias, 'audience': audience, 'token_ok': True,
        'minutes_remaining': 60, 'token_audience': 'graph',
        'audience_mismatch': False, 'error': None,
    })
    monkeypatch.setattr(probe_mod, 'probe_profile_coverage',
                        lambda alias, **kw: {'graph': True, 'outlook': False})
    report = cli_mod.build_report(coverage=True)
    assert report['profiles'][0]['coverage'] == {'graph': True, 'outlook': False}
