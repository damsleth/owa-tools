"""Pure manifest parsing tests - no network, no auth."""
import pytest

from owa_core.errors import InternalError, UsageError
from owa_vids import manifest as manifest_mod

SYNTH = '''<?xml version="1.0" encoding="utf-8"?>
<MPD mediaPresentationDuration="PT0H0M30S">
<Period>
<AdaptationSet contentType="video" width="1280" height="720">
<Representation id="v1" codecs="avc1.64001f" width="1280" height="720" bandwidth="1000"/>
<SegmentTemplate initialization="init-$RepresentationID$.mp4&amp;a=1" media="seg-$RepresentationID$-$Time$.m4s" timescale="1000">
<SegmentTimeline><S t="0" d="10000" r="2"/></SegmentTimeline>
</SegmentTemplate>
</AdaptationSet>
<AdaptationSet contentType="audio">
<Representation id="a1" codecs="mp4a.40.2" bandwidth="100"/>
<SegmentTemplate initialization="ainit-$RepresentationID$.mp4" media="aseg-$RepresentationID$-$Time$.m4s" timescale="1000">
<SegmentTimeline><S t="0" d="15000" r="-1"/></SegmentTimeline>
</SegmentTemplate>
</AdaptationSet>
</Period>
<BaseURL>https://region.svc.ms/v/</BaseURL>
</MPD>'''


def test_parse_iso_duration_full_form():
    xml = 'mediaPresentationDuration="PT1H2M3.5S"'
    assert manifest_mod._parse_iso_duration(xml) == 3723.5


def test_parse_iso_duration_seconds_only():
    xml = 'mediaPresentationDuration="PT45S"'
    assert manifest_mod._parse_iso_duration(xml) == 45.0


def test_parse_iso_duration_with_days():
    xml = 'mediaPresentationDuration="P1DT1H"'
    assert manifest_mod._parse_iso_duration(xml) == 90000.0


def test_parse_iso_duration_missing_returns_none():
    assert manifest_mod._parse_iso_duration('<MPD>') is None


def test_expand_timeline_normal():
    tl = '<S t="0" d="100" r="2"/>'
    assert manifest_mod._expand_timeline(tl, 1, None) == [0, 100, 200]


def test_expand_timeline_open_ended_r_minus_1():
    # r=-1 fills until the next <S>'s t.
    tl = '<S t="0" d="50" r="-1"/><S t="200" d="100"/>'
    assert manifest_mod._expand_timeline(tl, 1, None) == [0, 50, 100, 150, 200]


def test_expand_timeline_r_minus_1_uses_period_end():
    # r=-1 on the last segment bounds at duration_s * timescale.
    tl = '<S t="0" d="50" r="-1"/>'
    assert manifest_mod._expand_timeline(tl, 10, 20) == [0, 50, 100, 150]


def test_expand_timeline_r_minus_1_without_duration_raises():
    tl = '<S t="0" d="50" r="-1"/>'
    with pytest.raises(InternalError):
        manifest_mod._expand_timeline(tl, 10, None)


def test_parse_manifest_encrypted_raises_usage_error():
    xml = '<MPD><ContentProtection schemeIdUri="x"/></MPD>'
    with pytest.raises(UsageError):
        manifest_mod.parse_manifest(xml)


def test_parse_manifest_returns_track_dict():
    man = manifest_mod.parse_manifest(SYNTH)

    assert man['base'] == 'https://region.svc.ms/v/'
    assert man['duration'] == 30.0
    assert set(man['tracks']) == {'video', 'audio'}

    video = man['tracks']['video']
    # $RepresentationID$ substituted, &amp; unescaped, BaseURL prefixed.
    assert video['init'] == 'https://region.svc.ms/v/init-v1.mp4&a=1'
    assert video['media_tmpl'] == 'https://region.svc.ms/v/seg-v1-$Time$.m4s'
    assert video['times'] == [0, 10000, 20000]
    assert video['codecs'] == 'avc1.64001f'
    assert video['width'] == 1280
    assert video['height'] == 720

    audio = man['tracks']['audio']
    # Open-ended r=-1 audio timeline bounded by the 30s presentation duration.
    assert audio['times'] == [0, 15000]


def test_with_token_replaces_existing_access_token():
    url = 'https://h/seg.m4s?a=1&access_token=old'
    out = manifest_mod._with_token(url, 'new')
    assert 'access_token=new' in out
    assert 'old' not in out
    assert 'a=1' in out


def test_build_manifest_url_carries_docid_and_token():
    class JobStub:
        docid = 'https://h/x?version=Published'
        ctag = 'ct'
        region = 'r-mediap.svc.ms'

    url = manifest_mod.build_manifest_url(JobStub(), 'tok')
    assert url.startswith('https://r-mediap.svc.ms/transform/videomanifest?')
    assert 'format=dash' in url
    assert 'access_token=tok' in url
    # No enableEncryption param: the clear path is the whole point.
    assert 'enableEncryption' not in url
