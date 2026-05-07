"""Tests for owa_cal.profiles (local store + piggy listing) and the
`owa-cal profiles` CLI command."""
import json
import sys

from owa_cal import profiles as profiles_mod


# ---------------------------------------------------------------------------
# Local store
# ---------------------------------------------------------------------------

def test_load_local_returns_empty_dict_when_file_missing(tmp_profiles):
    assert profiles_mod.load_local() == {}


def test_add_local_creates_file(tmp_profiles):
    new = profiles_mod.add_local('brkh', 'https://example.invalid/feed')
    assert new is True
    assert tmp_profiles.exists()
    data = json.loads(tmp_profiles.read_text())
    assert data == {'brkh': {'webcal_url': 'https://example.invalid/feed'}}


def test_add_local_update_returns_false(tmp_profiles):
    profiles_mod.add_local('brkh', 'https://a.invalid')
    new = profiles_mod.add_local('brkh', 'https://b.invalid')
    assert new is False
    data = json.loads(tmp_profiles.read_text())
    assert data['brkh']['webcal_url'] == 'https://b.invalid'


def test_delete_local_removes_entry(tmp_profiles):
    profiles_mod.add_local('brkh', 'https://example.invalid')
    assert profiles_mod.delete_local('brkh') is True
    assert profiles_mod.load_local() == {}


def test_delete_local_missing_returns_false(tmp_profiles):
    assert profiles_mod.delete_local('nope') is False


def test_save_local_uses_0600_perms(tmp_profiles):
    profiles_mod.add_local('x', 'https://x.invalid')
    mode = tmp_profiles.stat().st_mode & 0o777
    assert mode == 0o600


def test_load_local_tolerates_corrupt_json(tmp_profiles):
    tmp_profiles.parent.mkdir(parents=True, exist_ok=True)
    tmp_profiles.write_text('{not json')
    assert profiles_mod.load_local() == {}


def test_load_local_tolerates_non_object_root(tmp_profiles):
    tmp_profiles.parent.mkdir(parents=True, exist_ok=True)
    tmp_profiles.write_text('["a", "b"]')
    assert profiles_mod.load_local() == {}


# ---------------------------------------------------------------------------
# piggy_aliases parser
# ---------------------------------------------------------------------------

def _fake_subprocess_run(monkeypatch, stdout, returncode=0):
    class FakeProc:
        pass

    fp = FakeProc()
    fp.stdout = stdout
    fp.returncode = returncode

    monkeypatch.setattr(profiles_mod.shutil, 'which', lambda _: '/usr/bin/owa-piggy')
    monkeypatch.setattr(
        profiles_mod.subprocess, 'run',
        lambda *a, **kw: fp,
    )


def test_piggy_aliases_parses_real_format(monkeypatch):
    _fake_subprocess_run(monkeypatch, '   brkh\n   crayon\n   dno\n * swon\n')
    aliases, default = profiles_mod.piggy_aliases()
    assert aliases == {'brkh', 'crayon', 'dno', 'swon'}
    assert default == 'swon'


def test_piggy_aliases_no_default(monkeypatch):
    _fake_subprocess_run(monkeypatch, '   alpha\n   beta\n')
    aliases, default = profiles_mod.piggy_aliases()
    assert aliases == {'alpha', 'beta'}
    assert default == ''


def test_piggy_aliases_returns_empty_when_owa_piggy_missing(monkeypatch):
    monkeypatch.setattr(profiles_mod.shutil, 'which', lambda _: None)
    aliases, default = profiles_mod.piggy_aliases()
    assert aliases == set()
    assert default == ''


def test_piggy_aliases_returns_empty_on_error_exit(monkeypatch):
    _fake_subprocess_run(monkeypatch, '', returncode=2)
    aliases, default = profiles_mod.piggy_aliases()
    assert aliases == set()
    assert default == ''


def test_piggy_aliases_skips_lines_with_spaces(monkeypatch):
    """Lines that look like a banner / error sentence (multiple words)
    are dropped - the parser only accepts bareword aliases."""
    _fake_subprocess_run(monkeypatch, 'header line here\n   alpha\n')
    aliases, _default = profiles_mod.piggy_aliases()
    assert aliases == {'alpha'}


# ---------------------------------------------------------------------------
# CLI: owa-cal profiles list/add/delete
# ---------------------------------------------------------------------------

def test_profiles_list_json(
    tmp_profiles, stub_piggy_aliases, clean_env, monkeypatch, capsys,
):
    profiles_mod.add_local('brkh', 'https://example.invalid')
    stub_piggy_aliases(['brkh', 'crayon', 'swon'], 'swon')
    monkeypatch.setattr(sys, 'argv', ['owa-cal', 'profiles'])
    from owa_cal.cli import main
    rc = main()
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    # owa-cal entries first, alphabetical, then owa-piggy entries.
    assert payload[0]['source'] == 'owa-cal'
    assert payload[0]['alias'] == 'brkh'
    assert payload[0]['shadows_owa_piggy'] is True
    piggy_entries = [e for e in payload if e['source'] == 'owa-piggy']
    assert {e['alias'] for e in piggy_entries} == {'brkh', 'crayon', 'swon'}
    brkh_piggy = next(e for e in piggy_entries if e['alias'] == 'brkh')
    assert brkh_piggy['shadowed_by_owa_cal'] is True
    swon_piggy = next(e for e in piggy_entries if e['alias'] == 'swon')
    assert swon_piggy['default'] is True


def test_profiles_list_pretty(
    tmp_profiles, stub_piggy_aliases, clean_env, monkeypatch, capsys,
):
    profiles_mod.add_local('brkh', 'https://example.invalid')
    stub_piggy_aliases(['brkh', 'swon'], 'swon')
    monkeypatch.setattr(sys, 'argv', ['owa-cal', 'profiles', '--pretty'])
    from owa_cal.cli import main
    main()
    out = capsys.readouterr().out
    assert 'owa-cal (webcal):' in out
    assert 'owa-piggy (oauth):' in out
    assert '[also defined in owa-piggy; this wins]' in out
    assert '[shadowed by owa-cal' in out
    assert '* swon' in out


def test_profiles_list_does_not_leak_url(
    tmp_profiles, stub_piggy_aliases, clean_env, monkeypatch, capsys,
):
    """The URL is a bearer secret - it must not appear in either JSON
    or --pretty output."""
    profiles_mod.add_local('brkh', 'https://secret.invalid/feed?key=TOPSECRET')
    monkeypatch.setattr(sys, 'argv', ['owa-cal', 'profiles', '--pretty'])
    from owa_cal.cli import main
    main()
    out = capsys.readouterr().out
    assert 'TOPSECRET' not in out
    assert 'secret.invalid' not in out

    monkeypatch.setattr(sys, 'argv', ['owa-cal', 'profiles'])
    main()
    out = capsys.readouterr().out
    assert 'TOPSECRET' not in out


def test_profiles_add_creates_entry(
    tmp_profiles, stub_piggy_aliases, clean_env, monkeypatch, capsys,
):
    monkeypatch.setattr(sys, 'argv', [
        'owa-cal', 'profiles', 'add', 'brkh',
        '--webcal', 'https://example.invalid/feed',
    ])
    from owa_cal.cli import main
    rc = main()
    err = capsys.readouterr().err
    assert rc == 0
    assert "profile 'brkh' created" in err
    assert profiles_mod.load_local() == {
        'brkh': {'webcal_url': 'https://example.invalid/feed'},
    }


def test_profiles_add_warns_on_piggy_collision(
    tmp_profiles, stub_piggy_aliases, clean_env, monkeypatch, capsys,
):
    stub_piggy_aliases(['brkh'])
    monkeypatch.setattr(sys, 'argv', [
        'owa-cal', 'profiles', 'add', 'brkh',
        '--webcal', 'https://example.invalid/feed',
    ])
    from owa_cal.cli import main
    main()
    err = capsys.readouterr().err
    assert "'brkh' is also an owa-piggy profile" in err


def test_profiles_add_requires_alias_and_webcal(
    tmp_profiles, stub_piggy_aliases, clean_env, monkeypatch, capsys,
):
    from owa_cal.cli import main
    monkeypatch.setattr(sys, 'argv', ['owa-cal', 'profiles', 'add'])
    assert main() != 0
    monkeypatch.setattr(sys, 'argv', ['owa-cal', 'profiles', 'add', 'x'])
    assert main() != 0


def test_profiles_delete_removes_entry(
    tmp_profiles, stub_piggy_aliases, clean_env, monkeypatch, capsys,
):
    profiles_mod.add_local('brkh', 'https://example.invalid')
    monkeypatch.setattr(sys, 'argv', ['owa-cal', 'profiles', 'delete', 'brkh'])
    from owa_cal.cli import main
    assert main() == 0
    assert profiles_mod.load_local() == {}


def test_profiles_delete_redirects_for_piggy_alias(
    tmp_profiles, stub_piggy_aliases, clean_env, monkeypatch, capsys,
):
    """Deleting a name that only exists as an owa-piggy profile must
    redirect the user to `owa-piggy profiles delete`, not silently
    succeed or report 'no such profile'."""
    stub_piggy_aliases(['work'])
    monkeypatch.setattr(sys, 'argv', ['owa-cal', 'profiles', 'delete', 'work'])
    from owa_cal.cli import main
    rc = main()
    err = capsys.readouterr().err
    assert rc == 2
    assert 'owa-piggy profiles delete work' in err


def test_profiles_delete_unknown_alias(
    tmp_profiles, stub_piggy_aliases, clean_env, monkeypatch, capsys,
):
    monkeypatch.setattr(sys, 'argv', ['owa-cal', 'profiles', 'delete', 'ghost'])
    from owa_cal.cli import main
    assert main() != 0
    assert "no owa-cal profile named 'ghost'" in capsys.readouterr().err


def test_profiles_unknown_subcommand(
    tmp_profiles, stub_piggy_aliases, clean_env, monkeypatch, capsys,
):
    monkeypatch.setattr(sys, 'argv', ['owa-cal', 'profiles', 'frobnicate'])
    from owa_cal.cli import main
    assert main() != 0
