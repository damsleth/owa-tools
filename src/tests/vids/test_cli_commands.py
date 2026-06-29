"""In-process dispatch tests through cli.main() with mocked boundaries."""
import json

from owa_vids import cli
from owa_vids import manifest as manifest_mod
from owa_vids import resolve as resolve_mod
from owa_vids import segments as segments_mod


def _job(**overrides):
    fields = dict(
        spo_host='contoso-my.sharepoint.com',
        docid='https://contoso-my.sharepoint.com/x?version=Published',
        ctag='ct', region='swon-mediap.svc.ms',
        title='All Hands.mp4', drive_id='b!DRV', item_id='01ITEM',
    )
    fields.update(overrides)
    return resolve_mod.Job(**fields)


_MAN = {
    'base': 'https://swon-mediap.svc.ms/v/',
    'duration': 12.5,
    'tracks': {
        'video': {'init': 'i', 'media_tmpl': 'm', 'times': [0, 1],
                  'codecs': 'avc1', 'width': 1280, 'height': 720},
        'audio': {'init': 'i', 'media_tmpl': 'm', 'times': [0, 1],
                  'codecs': 'mp4a', 'width': None, 'height': None},
    },
}


def _mock_pipeline(monkeypatch, job=None, man=None):
    job = job or _job()
    man = man if man is not None else _MAN
    monkeypatch.setattr(resolve_mod, '_resolve', lambda *a, **k: job)
    monkeypatch.setattr(manifest_mod, '_manifest',
                        lambda *a, **k: (man, {'token': 't', 'refresh': lambda: 't'}))
    return job


MANIFEST_ARGS = ['--manifest-url',
                 'https://swon-mediap.svc.ms/transform/videomanifest?docid=x&format=dash']


def test_main_schema_returns_tool_name(capsys, clean_env):
    rc = cli.main(['schema'])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload['tool'] == 'owa-vids'


def test_main_info_json_output(capsys, clean_env, tmp_config, monkeypatch):
    _mock_pipeline(monkeypatch)
    rc = cli.main(['info', *MANIFEST_ARGS])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out['duration_s'] == 12.5
    assert out['title'] == 'All Hands.mp4'
    assert out['video_segments'] == 2
    assert out['encrypted'] is False


def test_main_info_pretty_output(capsys, clean_env, tmp_config, monkeypatch):
    _mock_pipeline(monkeypatch)
    rc = cli.main(['info', *MANIFEST_ARGS, '--pretty'])
    assert rc == 0
    out = capsys.readouterr().out
    assert 'All Hands.mp4' in out
    assert '1280x720' in out


def test_main_get_writes_file_and_outputs_json(capsys, clean_env, tmp_config,
                                               monkeypatch, tmp_path):
    _mock_pipeline(monkeypatch)
    out_file = tmp_path / 'meeting.mp4'

    monkeypatch.setattr(cli.shutil, 'which', lambda _: '/usr/local/bin/ffmpeg')
    monkeypatch.setattr(segments_mod, 'download_track',
                        lambda http, name, tr, holder, workdir, **kw: f'{workdir}/{name}.m4s')

    def fake_mux(track_files, out_path, debug=False):
        with open(out_path, 'wb') as fh:
            fh.write(b'x' * 42)

    monkeypatch.setattr(segments_mod, 'mux', fake_mux)

    rc = cli.main(['get', *MANIFEST_ARGS, '--out', str(out_file),
                   '--workdir', str(tmp_path)])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {'out': str(out_file), 'bytes': 42, 'title': 'All Hands.mp4'}


def test_main_get_without_ffmpeg_exits_usage(capsys, clean_env, tmp_config, monkeypatch):
    _mock_pipeline(monkeypatch)
    monkeypatch.setattr(cli.shutil, 'which', lambda _: None)
    rc = cli.main(['get', *MANIFEST_ARGS])
    assert rc == 2
    assert 'ffmpeg' in capsys.readouterr().err


def test_main_check_reports_ok(capsys, clean_env, tmp_config, monkeypatch, tmp_path):
    _mock_pipeline(monkeypatch)
    monkeypatch.setattr(segments_mod, 'download_track',
                        lambda http, name, tr, holder, workdir, **kw: f'{workdir}/{name}.m4s')
    rc = cli.main(['check', *MANIFEST_ARGS, '--workdir', str(tmp_path)])
    assert rc == 0
    captured = capsys.readouterr()
    assert 'CHECK OK' in captured.err
    assert json.loads(captured.out)['ok'] is True


def test_main_agent_mode_envelope(capsys, clean_env, tmp_config, monkeypatch):
    _mock_pipeline(monkeypatch)
    rc = cli.main(['--agent', 'info', *MANIFEST_ARGS])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload['_owa']['tool'] == 'owa-vids'
    assert payload['_owa']['command'] == 'info'
    assert payload['data']['duration_s'] == 12.5


def test_main_err_json_on_auth_failure(capsys, clean_env, tmp_config, monkeypatch):
    # Real resolve path (no drive ids in the docid, so no best-effort title
    # fetch), broker missing -> AuthExpiredError when the SPO token is minted.
    monkeypatch.setattr('owa_core.auth.shutil.which', lambda _: None)
    rc = cli.main(['--err-json', 'info', '--manifest-url',
                   'https://swon-mediap.svc.ms/transform/videomanifest'
                   '?docid=https%3A%2F%2Fcontoso-my.sharepoint.com%2Fx&format=dash'])
    assert rc == 11
    payload = json.loads(capsys.readouterr().err)
    assert payload['error']['code'] == 'AUTH_EXPIRED'
    assert payload['error']['tool'] == 'owa-vids'
    assert payload['error']['command'] == 'info'


def test_main_config_verb_unauthenticated(capsys, clean_env, tmp_config, monkeypatch):
    monkeypatch.setattr('owa_core.auth.shutil.which', lambda _: None)
    rc = cli.main(['config'])
    assert rc == 0
    err = capsys.readouterr().err
    assert 'Config file' in err
    assert 'region' in err


def test_main_config_persists_profile_and_region(capsys, clean_env, tmp_config):
    rc = cli.main(['config', '--profile', 'swon', '--region', 'SWON-mediap.svc.ms'])
    assert rc == 0
    from owa_vids import config as config_mod
    saved = config_mod.load_config()
    assert saved['owa_piggy_profile'] == 'swon'
    assert saved['region'] == 'swon-mediap.svc.ms'  # normalized to lowercase


def test_main_debug_flag_sets_config(clean_env, tmp_config, monkeypatch, capsys):
    seen = {}

    def fake_resolve(manifest_url, embed_url, source_url, region, config, debug):
        seen['debug'] = debug
        return _job()

    monkeypatch.setattr(resolve_mod, '_resolve', fake_resolve)
    monkeypatch.setattr(manifest_mod, '_manifest',
                        lambda *a, **k: (_MAN, {'token': 't', 'refresh': lambda: 't'}))

    rc = cli.main(['--debug', 'info', *MANIFEST_ARGS])
    assert rc == 0
    assert seen['debug'] is True
    capsys.readouterr()  # drain


def test_main_get_rejects_both_track_filters(capsys, clean_env, tmp_config):
    rc = cli.main(['get', *MANIFEST_ARGS, '--video-only', '--audio-only'])
    assert rc == 2
    assert 'only one of' in capsys.readouterr().err
