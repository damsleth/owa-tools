"""Segment loop and mux tests - Http and subprocess boundaries mocked."""
import os

import pytest

from owa_core.errors import NetworkError
from owa_vids import segments as segments_mod


class FakeHttp:
    """Scripted (status, body) responses; records every URL fetched."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, headers=None, *, tries=8):
        self.calls.append(url)
        if not self.responses:
            raise AssertionError('unexpected extra request: ' + url)
        out = self.responses.pop(0)
        return out if isinstance(out, tuple) else (200, out)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(segments_mod.time, 'sleep', lambda *_: None)


def test_get_segment_success():
    http = FakeHttp([(200, b'\x00' * 188)])
    data = segments_mod._get_segment(http, 'https://h/seg?x=1', {'token': 't'})
    assert data == b'\x00' * 188
    assert 'access_token=t' in http.calls[0]


def test_get_segment_auth_retry_on_401():
    http = FakeHttp([(401, b''), (200, b'segment-data')])
    refreshes = []

    def refresh():
        refreshes.append(1)
        return 'new-token'

    holder = {'token': 'expired', 'refresh': refresh}
    data = segments_mod._get_segment(http, 'https://h/seg', holder)

    assert data == b'segment-data'
    assert len(refreshes) == 1
    assert holder['token'] == 'new-token'
    assert 'access_token=expired' in http.calls[0]
    assert 'access_token=new-token' in http.calls[1]


def test_get_segment_exhausted_retries_raises():
    http = FakeHttp([(401, b'')] * 6)
    with pytest.raises(NetworkError):
        segments_mod._get_segment(http, 'https://h/seg', {'token': 't'}, tries=6)


def test_get_segment_error_message_omits_query(monkeypatch):
    http = FakeHttp([(404, b'')] * 6)
    with pytest.raises(NetworkError) as exc:
        segments_mod._get_segment(http, 'https://h/seg?access_token=SECRET', {'token': 't'}, tries=6)
    assert 'SECRET' not in str(exc.value)


def test_download_track_resumes(tmp_path):
    workdir = str(tmp_path)
    tr = {
        'init': 'https://h/init',
        'media_tmpl': 'https://h/seg-$Time$.m4s',
        'times': [0, 100],
    }
    # Pre-create every segment: no fetch should happen.
    (tmp_path / 'video_init.m4s').write_bytes(b'INIT')
    (tmp_path / 'video_0000.m4s').write_bytes(b'AAAA')
    (tmp_path / 'video_0001.m4s').write_bytes(b'BBBB')

    http = FakeHttp([])  # raises on any request
    out = segments_mod.download_track(http, 'video', tr, {'token': 't'}, workdir)

    assert http.calls == []
    with open(out, 'rb') as fh:
        assert fh.read() == b'INITAAAABBBB'


def test_download_track_fetches_missing_segments(tmp_path):
    tr = {
        'init': 'https://h/init',
        'media_tmpl': 'https://h/seg-$Time$.m4s',
        'times': [0, 100],
    }
    http = FakeHttp([(200, b'I'), (200, b'A'), (200, b'B')])
    out = segments_mod.download_track(http, 'audio', tr, {'token': 't'}, str(tmp_path))

    assert len(http.calls) == 3
    assert 'seg-0.m4s' in http.calls[1]
    assert 'seg-100.m4s' in http.calls[2]
    with open(out, 'rb') as fh:
        assert fh.read() == b'IAB'
    # No stray .part files left behind.
    assert not [p for p in os.listdir(tmp_path) if p.endswith('.part')]


def test_download_track_limit_and_probe(tmp_path):
    tr = {
        'init': 'https://h/init',
        'media_tmpl': 'https://h/seg-$Time$.m4s',
        'times': [0, 100, 200, 300],
    }
    init = b'\x00\x00\x00\x18ftypiso6'
    seg = b'\x00\x00\x00\x10moofdata'
    http = FakeHttp([(200, init), (200, seg), (200, seg)])

    segments_mod.download_track(
        http, 'video', tr, {'token': 't'}, str(tmp_path), limit=2, probe=True,
    )
    assert len(http.calls) == 3  # init + 2 segments, not all 4


def test_download_track_probe_rejects_non_fmp4(tmp_path):
    tr = {'init': 'https://h/init', 'media_tmpl': 'https://h/s-$Time$', 'times': [0]}
    http = FakeHttp([(200, b'<html>not a video</html>')])
    from owa_core.errors import InternalError
    with pytest.raises(InternalError):
        segments_mod.download_track(
            http, 'video', tr, {'token': 't'}, str(tmp_path), probe=True,
        )


def test_mux_calls_ffmpeg(monkeypatch, tmp_path):
    seen = {}

    def fake_run(cmd, check=False):
        seen['cmd'] = cmd
        seen['check'] = check

    monkeypatch.setattr(segments_mod.subprocess, 'run', fake_run)
    out = str(tmp_path / 'out.mp4')
    segments_mod.mux({'video': 'v.m4s', 'audio': 'a.m4s'}, out)

    cmd = seen['cmd']
    assert cmd[0] == 'ffmpeg'
    assert cmd[cmd.index('-c') + 1] == 'copy'
    assert cmd[-1] == out
    assert cmd.count('-i') == 2
    assert seen['check'] is True


def test_mux_failure_raises_internal_error(monkeypatch):
    def fake_run(cmd, check=False):
        raise OSError('ffmpeg missing')

    monkeypatch.setattr(segments_mod.subprocess, 'run', fake_run)
    from owa_core.errors import InternalError
    with pytest.raises(InternalError):
        segments_mod.mux({'video': 'v.m4s'}, 'out.mp4')
