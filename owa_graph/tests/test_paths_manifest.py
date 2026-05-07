"""Path manifest loader + the hidden `__complete` subcommand the
completion scripts shell out to."""
import gzip
import io
import json
import sys

import pytest

from owa_graph import cli, paths as paths_mod


@pytest.fixture(autouse=True)
def _reset():
    paths_mod.reset_cache_for_tests()
    yield
    paths_mod.reset_cache_for_tests()


# --- loader contract -----------------------------------------------------

def test_known_endpoints_includes_v1_and_beta():
    eps = paths_mod.known_endpoints()
    assert 'v1.0' in eps
    assert 'beta' in eps


def test_v1_paths_include_well_known_routes():
    paths = paths_mod.all_paths('v1.0')
    assert '/me' in paths
    assert '/users' in paths
    # Templated key slot
    assert '/users/{id}' in paths


def test_unknown_endpoint_returns_empty_list():
    assert paths_mod.all_paths('nonexistent') == []


def test_load_failure_returns_empty(monkeypatch, tmp_path):
    monkeypatch.setattr(paths_mod, '_DATA_PATH', tmp_path / 'missing.json.gz')
    paths_mod.reset_cache_for_tests()
    assert paths_mod.all_paths('v1.0') == []
    assert paths_mod.known_endpoints() == []


def test_corrupt_gzip_returns_empty(monkeypatch, tmp_path):
    bad = tmp_path / 'paths.json.gz'
    bad.write_bytes(b'not a gzip stream')
    monkeypatch.setattr(paths_mod, '_DATA_PATH', bad)
    paths_mod.reset_cache_for_tests()
    assert paths_mod.all_paths('v1.0') == []


def test_loader_caches(monkeypatch, tmp_path):
    paths_mod.all_paths('v1.0')  # warm cache
    monkeypatch.setattr(paths_mod, '_DATA_PATH', tmp_path / 'missing.json.gz')
    # Cache hit: still returns real paths.
    assert '/me' in paths_mod.all_paths('v1.0')


# --- dump_paths formatting ----------------------------------------------

def test_dump_paths_emits_one_line_per_entry():
    buf = io.StringIO()
    written = paths_mod.dump_paths('v1.0', stream=buf)
    text = buf.getvalue()
    assert written > 1000   # we ship thousands
    assert text.count('\n') == written


def test_dump_paths_tolerates_broken_pipe(monkeypatch):
    class _Pipe:
        def __init__(self):
            self.n = 0
        def write(self, s):
            self.n += 1
            if self.n > 3:
                raise BrokenPipeError()
    written = paths_mod.dump_paths('v1.0', stream=_Pipe())
    # Returned count reflects what was successfully written, no
    # exception escapes.
    assert 0 < written


# --- __complete CLI subcommand ------------------------------------------

def test_complete_paths_subcommand_lists_v1(monkeypatch, capsys):
    monkeypatch.setattr(sys, 'argv', ['owa-graph', '__complete', 'paths', 'v1.0'])
    rc = cli.main()
    out = capsys.readouterr().out
    assert rc == 0
    assert '/me\n' in out
    assert '/users\n' in out


def test_complete_paths_default_endpoint_is_v1(monkeypatch, capsys):
    monkeypatch.setattr(sys, 'argv', ['owa-graph', '__complete', 'paths'])
    rc = cli.main()
    out = capsys.readouterr().out
    assert rc == 0
    assert '/me\n' in out


def test_complete_unknown_subtype_errors(monkeypatch, capsys):
    monkeypatch.setattr(sys, 'argv', ['owa-graph', '__complete', 'gibberish'])
    rc = cli.main()
    assert rc == 1


def test_complete_no_args_errors(monkeypatch):
    monkeypatch.setattr(sys, 'argv', ['owa-graph', '__complete'])
    assert cli.main() == 1


# --- shipped manifest sanity --------------------------------------------

def test_shipped_manifest_meets_target_path_count():
    """Plan v0.5 exit criteria: >5000 paths across v1.0 + beta."""
    total = len(paths_mod.all_paths('v1.0')) + len(paths_mod.all_paths('beta'))
    assert total > 5000, f'expected >5000 paths total, got {total}'


def test_paths_are_sorted_within_endpoint():
    """Sorted-ness is what makes prefix-filtering in compgen O(n) rather
    than `2n with shuffling. Cheap invariant to lock."""
    paths = paths_mod.all_paths('v1.0')
    assert paths == sorted(paths)
