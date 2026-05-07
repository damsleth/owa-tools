"""Tests for cli.build_report and exit-code policy."""
from owa_doctor import cli as cli_mod
from owa_doctor import probe as probe_mod


def test_build_report_no_piggy(monkeypatch):
    monkeypatch.setattr(probe_mod, 'probe_piggy', lambda: {
        'installed': False, 'version': None, 'path': None,
    })
    monkeypatch.setattr(probe_mod, 'probe_siblings', lambda: [])
    report = cli_mod.build_report()
    assert report['summary']['fail'] == 1
    assert cli_mod._exit_code_for(report) == 2


def test_build_report_all_ok(monkeypatch):
    monkeypatch.setattr(probe_mod, 'probe_piggy', lambda: {
        'installed': True, 'version': '0.7.1', 'path': '/x',
    })
    monkeypatch.setattr(probe_mod, 'probe_siblings', lambda: [])
    monkeypatch.setattr(probe_mod, 'list_piggy_profiles',
                        lambda: (['swon'], 'swon'))
    monkeypatch.setattr(probe_mod, 'probe_profile_token', lambda alias, audience='graph': {
        'alias': alias, 'audience': audience,
        'token_ok': True, 'minutes_remaining': 60,
        'token_audience': 'graph', 'error': None,
    })
    report = cli_mod.build_report()
    assert report['summary'] == {'ok': 1, 'warn': 0, 'fail': 0}
    assert cli_mod._exit_code_for(report) == 0


def test_build_report_warn(monkeypatch):
    monkeypatch.setattr(probe_mod, 'probe_piggy', lambda: {
        'installed': True, 'version': '0.7.1', 'path': '/x',
    })
    monkeypatch.setattr(probe_mod, 'probe_siblings', lambda: [])
    monkeypatch.setattr(probe_mod, 'list_piggy_profiles',
                        lambda: (['swon'], 'swon'))
    monkeypatch.setattr(probe_mod, 'probe_profile_token', lambda alias, audience='graph': {
        'alias': alias, 'audience': audience,
        'token_ok': True, 'minutes_remaining': 5,
        'token_audience': 'graph', 'error': None,
    })
    report = cli_mod.build_report()
    assert report['summary']['warn'] == 1
    assert cli_mod._exit_code_for(report) == 1


def test_build_report_no_tokens_skips_profile_probe(monkeypatch):
    called = {'n': 0}

    def fake_probe(alias, audience='graph'):
        called['n'] += 1
        return {}

    monkeypatch.setattr(probe_mod, 'probe_piggy', lambda: {
        'installed': True, 'version': '0.7.1', 'path': '/x',
    })
    monkeypatch.setattr(probe_mod, 'probe_siblings', lambda: [])
    monkeypatch.setattr(probe_mod, 'probe_profile_token', fake_probe)
    monkeypatch.setattr(probe_mod, 'list_piggy_profiles',
                        lambda: (['swon'], 'swon'))
    report = cli_mod.build_report(no_tokens=True)
    assert called['n'] == 0
    assert report['profiles'] == []
