"""Path-pattern matcher for scope hints.

Tests the matcher against the shipped scopes.json plus a synthetic
manifest to lock the segment/wildcard rules.
"""
import json

import pytest

from owa_graph import scopes as scopes_mod


@pytest.fixture(autouse=True)
def _reset_cache():
    scopes_mod.reset_cache_for_tests()
    yield
    scopes_mod.reset_cache_for_tests()


# --- segment matcher ------------------------------------------------------

def test_segments_match_literal_equal():
    assert scopes_mod._segments_match(['me', 'messages'], ['me', 'messages'])


def test_segments_match_wildcard_replaces_concrete_id():
    assert scopes_mod._segments_match(
        ['users', '{id}', 'manager'],
        ['users', '12345', 'manager'],
    )


def test_segments_match_rejects_length_mismatch():
    assert not scopes_mod._segments_match(['users'], ['users', '12345'])


def test_segments_match_rejects_literal_mismatch():
    assert not scopes_mod._segments_match(['me'], ['us'])


# --- normalize -------------------------------------------------------------

def test_normalize_drops_leading_slash():
    assert scopes_mod._normalize('/me/messages') == ['me', 'messages']
    assert scopes_mod._normalize('me/messages') == ['me', 'messages']


def test_normalize_strips_query_and_fragment():
    assert scopes_mod._normalize('/me/messages?$top=5') == ['me', 'messages']
    assert scopes_mod._normalize('/me/messages#anchor') == ['me', 'messages']


# --- against shipped manifest --------------------------------------------

def test_required_scopes_resolves_me():
    assert scopes_mod.required_scopes('GET', '/me') == ['User.Read']


def test_required_scopes_resolves_users_template():
    out = scopes_mod.required_scopes('GET', '/users/00000000-0000-0000-0000-000000000000/manager')
    assert out == ['User.Read.All']


def test_required_scopes_returns_empty_for_unknown_path():
    assert scopes_mod.required_scopes('GET', '/totally/made/up') == []


def test_required_scopes_returns_empty_for_unknown_verb():
    # The shipped manifest has GET /me but not POST /me.
    assert scopes_mod.required_scopes('POST', '/me') == []


def test_required_scopes_handles_query_string_in_path():
    assert scopes_mod.required_scopes('GET', '/me/messages?$top=5&$select=subject') == ['Mail.Read']


# --- cache + load failure ------------------------------------------------

def test_manifest_caches_after_first_load(monkeypatch):
    # The cache makes the loader a one-shot: after the first call,
    # _MANIFEST is populated and subsequent calls don't reach the
    # filesystem. Confirm by swapping the data path AFTER warming the
    # cache - subsequent calls should still return the original
    # manifest's results.
    scopes_mod.required_scopes('GET', '/me')  # warm cache
    monkeypatch.setattr(
        scopes_mod, '_DATA_PATH', scopes_mod._DATA_PATH.parent / 'does-not-exist.json',
    )
    # If the cache wasn't honored, the missing file would yield [].
    assert scopes_mod.required_scopes('GET', '/me') == ['User.Read']


def test_load_failure_yields_empty_results_silently(monkeypatch, tmp_path):
    # Point the manifest at a non-existent path; loader must not raise.
    monkeypatch.setattr(scopes_mod, '_DATA_PATH', tmp_path / 'missing.json')
    scopes_mod.reset_cache_for_tests()
    assert scopes_mod.required_scopes('GET', '/me') == []


def test_load_failure_on_malformed_json(monkeypatch, tmp_path):
    bad = tmp_path / 'scopes.json'
    bad.write_text('{this is not json')
    monkeypatch.setattr(scopes_mod, '_DATA_PATH', bad)
    scopes_mod.reset_cache_for_tests()
    assert scopes_mod.required_scopes('GET', '/me') == []


def test_manifest_skips_entries_missing_required_keys(monkeypatch, tmp_path):
    bad = tmp_path / 'scopes.json'
    bad.write_text(json.dumps({
        'scopes': [
            {'path': '/me', 'verb': 'GET', 'scopes': ['User.Read']},
            {'path': '/missing-verb', 'scopes': ['X']},
            {'verb': 'GET', 'scopes': ['X']},
            {'path': '/no-scopes', 'verb': 'GET'},
        ],
    }))
    monkeypatch.setattr(scopes_mod, '_DATA_PATH', bad)
    scopes_mod.reset_cache_for_tests()
    assert scopes_mod.required_scopes('GET', '/me') == ['User.Read']
    assert scopes_mod.required_scopes('GET', '/missing-verb') == []
    assert scopes_mod.required_scopes('GET', '/no-scopes') == []
