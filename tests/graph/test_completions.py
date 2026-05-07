"""Smoke tests for the shipped completion scripts.

We don't drive an interactive completion (that needs a tty), but we
do catch the common regressions: file present, parser accepts the
script, and the static command lists are in sync with what cli.py
actually exposes.
"""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from owa_graph import resources as resources_mod

ROOT = Path(__file__).resolve().parent.parent.parent
COMP = ROOT / 'completions'


def test_bash_script_exists_and_parses():
    f = COMP / 'owa-graph.bash'
    assert f.exists()
    rc = subprocess.run(['bash', '-n', str(f)], capture_output=True, text=True)
    assert rc.returncode == 0, rc.stderr


def test_zsh_script_exists_and_parses():
    f = COMP / 'owa-graph.zsh'
    assert f.exists()
    if not shutil.which('zsh'):
        pytest.skip('zsh not installed')
    rc = subprocess.run(['zsh', '-n', str(f)], capture_output=True, text=True)
    assert rc.returncode == 0, rc.stderr


def test_fish_script_exists_and_parses():
    f = COMP / 'owa-graph.fish'
    assert f.exists()
    if not shutil.which('fish'):
        pytest.skip('fish not installed')
    rc = subprocess.run(['fish', '-n', str(f)], capture_output=True, text=True)
    assert rc.returncode == 0, rc.stderr


# --- in-sync checks --------------------------------------------------------

def _scrape_groups(text):
    """Pull `me|mail|...|directory` alt list out of a completion script."""
    m = re.search(r'(me\|mail\|calendar[^)]*directory)', text)
    if not m:
        return None
    return m.group(1).split('|')


def test_bash_groups_match_known_groups():
    text = (COMP / 'owa-graph.bash').read_text()
    found = _scrape_groups(text)
    assert found is not None
    assert sorted(found) == sorted(resources_mod.known_groups())


def test_bash_lists_every_groups_shortcuts():
    """If a new shortcut lands in resources/<group>.py, the bash
    completion must learn about it. Locking this prevents drift."""
    text = (COMP / 'owa-graph.bash').read_text()
    for name in resources_mod.known_groups():
        module = resources_mod.load_group(name)
        for shortcut in module.COMMANDS:
            assert shortcut in text, (
                f'completions/owa-graph.bash is missing {name!r} shortcut '
                f'{shortcut!r}'
            )


def test_zsh_lists_every_groups_shortcuts():
    text = (COMP / 'owa-graph.zsh').read_text()
    for name in resources_mod.known_groups():
        module = resources_mod.load_group(name)
        for shortcut in module.COMMANDS:
            assert shortcut in text


def test_fish_lists_every_groups_shortcuts():
    text = (COMP / 'owa-graph.fish').read_text()
    for name in resources_mod.known_groups():
        module = resources_mod.load_group(name)
        for shortcut in module.COMMANDS:
            assert shortcut in text
