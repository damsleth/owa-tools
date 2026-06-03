"""Pretty-renderer tests - pure functions."""
from owa_vids import format as format_mod


def test_format_info_pretty_contains_title():
    out = format_mod.format_info_pretty({
        'title': 'All Hands.mp4',
        'duration_s': 1714.0,
        'width': 1280, 'height': 720,
        'video_codecs': 'avc1.64001f', 'audio_codecs': 'mp4a.40.2',
        'video_segments': 172, 'audio_segments': 172,
        'region': 'globex-mediap.svc.ms',
    })
    assert 'All Hands.mp4' in out
    assert '1714.0s' in out
    assert '1280x720' in out
    assert '172 video, 172 audio' in out
    assert 'globex-mediap.svc.ms' in out


def test_format_info_pretty_handles_missing_title():
    out = format_mod.format_info_pretty({})
    assert '(untitled)' in out


def test_format_get_pretty_shows_path_and_size():
    out = format_mod.format_get_pretty(
        {'out': 'meeting.mp4', 'bytes': 123456, 'title': 'Meeting'},
    )
    assert 'meeting.mp4' in out
    assert '123456' in out
