"""Human-readable rendering for `--pretty`."""


def _row(cells, widths):
    parts = []
    for cell, w in zip(cells, widths):
        s = str(cell) if cell is not None else '-'
        parts.append(s.ljust(w))
    return '  '.join(parts).rstrip()


def format_report_pretty(report):
    """Render the doctor report as a compact multi-section table."""
    lines = []

    piggy = report.get('owa_piggy') or {}
    if piggy.get('installed'):
        lines.append(
            f"owa-piggy: ok ({piggy.get('version') or '?'}) "
            f"at {piggy.get('path')}"
        )
    else:
        lines.append('owa-piggy: NOT FOUND on PATH')

    siblings = report.get('siblings') or []
    if siblings:
        lines.append('')
        lines.append('Siblings:')
        widths = (14, 5, 10)
        lines.append('  ' + _row(('cli', 'state', 'version'), widths))
        for s in siblings:
            state = 'ok' if s.get('installed') else 'missing'
            lines.append('  ' + _row(
                (s.get('name'), state, s.get('version') or '-'),
                widths,
            ))

    profiles = report.get('profiles') or []
    if profiles:
        lines.append('')
        lines.append('Profiles (audience=graph):')
        widths = (12, 7, 8, 10, 40)
        lines.append('  ' + _row(
            ('alias', 'default', 'state', 'mins-left', 'note'),
            widths,
        ))
        for p in profiles:
            lines.append('  ' + _row((
                p.get('alias'),
                'yes' if p.get('default') else '',
                p.get('state'),
                p.get('minutes_remaining') if p.get('minutes_remaining') is not None else '-',
                (p.get('error') or '')[:40],
            ), widths))

    summary = report.get('summary') or {}
    if summary:
        lines.append('')
        lines.append(
            f"Summary: {summary.get('ok', 0)} ok, "
            f"{summary.get('warn', 0)} warn, "
            f"{summary.get('fail', 0)} fail"
        )

    return '\n'.join(lines)
