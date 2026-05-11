"""Validation for the AGENTS.md progressive-disclosure mesh."""
from pathlib import Path

from owa_core.secrets import contains_secret

ROOT = Path(__file__).resolve().parents[2]

INDEXED_PATHS = [
    '.plans/',
    '.github/AGENTS.md',
    'src/owa_core/AGENTS.md',
    'src/owa/AGENTS.md',
    'src/owa_cal/AGENTS.md',
    'src/owa_mail/AGENTS.md',
    'src/owa_graph/AGENTS.md',
    'src/owa_doctor/AGENTS.md',
    'src/owa_people/AGENTS.md',
    'src/owa_sched/AGENTS.md',
    'src/owa_drive/AGENTS.md',
    'src/tests/AGENTS.md',
    'src/tests/contract/AGENTS.md',
    'src/tests/compat/AGENTS.md',
    'src/tests/security/AGENTS.md',
    'docs/AGENTS.md',
    'src/scripts/AGENTS.md',
]

RUNTIME_PACKAGES = [
    'owa',
    'owa_core',
    'owa_cal',
    'owa_mail',
    'owa_graph',
    'owa_doctor',
    'owa_people',
    'owa_sched',
    'owa_drive',
]


def _agents_files():
    return sorted(path for path in ROOT.rglob('AGENTS.md') if '.plans' not in path.parts)


def test_root_agents_indexes_expected_paths():
    root_agents = (ROOT / 'AGENTS.md').read_text(encoding='utf-8')
    for path in INDEXED_PATHS:
        assert f'| `{path}` |' in root_agents
        if path != '.plans/':
            assert (ROOT / path).exists(), path


def test_every_runtime_package_has_local_agents_file():
    for package in RUNTIME_PACKAGES:
        assert (ROOT / 'src' / package / 'AGENTS.md').exists()


def test_local_agents_files_include_nearest_tests_or_verify_command():
    for path in _agents_files():
        if path == ROOT / 'AGENTS.md':
            continue
        text = path.read_text(encoding='utf-8')
        assert 'Nearest tests:' in text or 'Verify:' in text, path


def test_agents_files_do_not_contain_secret_shapes():
    for path in _agents_files():
        assert not contains_secret(path.read_text(encoding='utf-8')), path
