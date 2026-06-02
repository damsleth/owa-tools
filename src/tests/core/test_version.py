"""Tests for suite version helpers."""
from importlib.metadata import PackageNotFoundError

from owa_core import version as version_mod


def test_suite_version_prefers_installed_distribution(monkeypatch):
    monkeypatch.setattr(version_mod, 'version', lambda name: '9.8.7')
    assert version_mod.suite_version() == '9.8.7'


def test_suite_version_falls_back_to_pyproject(monkeypatch):
    def missing(name):
        raise PackageNotFoundError(name)

    monkeypatch.setattr(version_mod, 'version', missing)
    monkeypatch.setattr(version_mod, '_version_from_root_pyproject', lambda: '0.1.0')
    assert version_mod.suite_version() == '0.1.0'


def test_suite_version_uses_final_fallback(monkeypatch):
    def missing(name):
        raise PackageNotFoundError(name)

    monkeypatch.setattr(version_mod, 'version', missing)
    monkeypatch.setattr(version_mod, '_version_from_root_pyproject', lambda: None)
    assert version_mod.suite_version() == version_mod.FALLBACK_VERSION


def test_binary_version_includes_binary_name(monkeypatch):
    monkeypatch.setattr(version_mod, 'suite_version', lambda: '1.2.3')
    assert version_mod.binary_version('owa-mail') == 'owa-mail 1.2.3'


def test_root_pyproject_version_parser_reads_current_project():
    assert version_mod._version_from_root_pyproject() == '0.6.1'
