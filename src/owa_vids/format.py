"""Pretty renderers for --pretty output. Plain text, no ANSI."""


def format_info_pretty(out):
    return "\n".join([
        f"Title      : {out.get('title') or '(untitled)'}",
        f"Duration   : {out.get('duration_s')}s",
        f"Resolution : {out.get('width')}x{out.get('height')}  "
        f"({out.get('video_codecs')} / {out.get('audio_codecs')})",
        f"Segments   : {out.get('video_segments')} video, {out.get('audio_segments')} audio",
        f"Region     : {out.get('region')}",
    ])


def format_get_pretty(result):
    title = result.get('title') or '(untitled)'
    return f"{title}: wrote {result.get('bytes')} bytes -> {result.get('out')}"
