"""Human-readable rendering for `--pretty`."""
from .dates import parse_local_iso


def _fmt_iso(s):
    if not s:
        return '-'
    try:
        dt = parse_local_iso(s)
        return dt.strftime('%Y-%m-%d %H:%M')
    except Exception:
        return s


def format_availability_pretty(attendees):
    if not attendees:
        return '(no attendees)'
    blocks = []
    for a in attendees:
        header = a.get('email') or '(unknown)'
        if a.get('error'):
            blocks.append(f'{header}\n  ERROR: {a["error"]}')
            continue
        busy = a.get('busy') or []
        if not busy:
            blocks.append(f'{header}\n  (no busy items in window)')
            continue
        lines = [header]
        for b in busy:
            lines.append(
                f"  {_fmt_iso(b.get('start'))} - {_fmt_iso(b.get('end'))} "
                f"[{b.get('status')}] {b.get('subject') or ''}".rstrip()
            )
        blocks.append('\n'.join(lines))
    return '\n\n'.join(blocks)


def format_slots_pretty(slots):
    if not slots:
        return '(no open slots)'
    lines = []
    for start, end in slots:
        lines.append(f"  {_fmt_iso(start)} - {_fmt_iso(end)}")
    return 'Open slots:\n' + '\n'.join(lines)
