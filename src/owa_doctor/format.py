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
    if not piggy.get('installed'):
        lines.append('owa-piggy: NOT FOUND on PATH')
    elif not piggy.get('reachable', True):
        lines.append(
            f"owa-piggy: UNREACHABLE at {piggy.get('path')} "
            "(installed but did not respond)"
        )
    else:
        lines.append(
            f"owa-piggy: ok ({piggy.get('version') or '?'}) "
            f"at {piggy.get('path')}"
        )

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
            note = p.get('error') or ''
            if not note and p.get('audience_mismatch'):
                note = f"audience mismatch (got {p.get('token_audience') or '?'})"
            lines.append('  ' + _row((
                p.get('alias'),
                'yes' if p.get('default') else '',
                p.get('state'),
                p.get('minutes_remaining') if p.get('minutes_remaining') is not None else '-',
                note[:40],
            ), widths))

    coverage_rows = [(p.get('alias'), p['coverage']) for p in profiles if p.get('coverage')]
    if coverage_rows:
        audiences = sorted({a for _, cov in coverage_rows for a in cov})
        lines.append('')
        lines.append('Coverage (audiences obtainable):')
        widths = (12,) + tuple(max(len(a), 5) + 1 for a in audiences)
        lines.append('  ' + _row(('alias', *audiences), widths))
        for alias, cov in coverage_rows:
            cells = (alias, *('yes' if cov.get(a) else 'no' for a in audiences))
            lines.append('  ' + _row(cells, widths))

    summary = report.get('summary') or {}
    if summary:
        lines.append('')
        lines.append(
            f"Summary: {summary.get('ok', 0)} ok, "
            f"{summary.get('warn', 0)} warn, "
            f"{summary.get('fail', 0)} fail"
        )

    return '\n'.join(lines)
