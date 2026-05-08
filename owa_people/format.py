"""Human-readable rendering for `--pretty`."""
from owa_core.format import truncate as _truncate_unicode


def _truncate(s, n):
    # ASCII '...' marker matches the historical look of this tool.
    return _truncate_unicode(s, n, suffix='...')


def format_people_pretty(people):
    if not people:
        return '(no matches)'
    rows = []
    rows.append(('name', 'email', 'title', 'company'))
    for p in people:
        rows.append((
            _truncate(p.get('displayName'), 28),
            _truncate(p.get('email'), 36),
            _truncate(p.get('jobTitle'), 28),
            _truncate(p.get('companyName'), 20),
        ))
    widths = [max(len(r[i]) for r in rows) for i in range(4)]
    out = []
    for row in rows:
        out.append('  '.join(c.ljust(w) for c, w in zip(row, widths)).rstrip())
    return '\n'.join(out)


def format_person_pretty(p):
    if not p:
        return '(no person)'
    lines = [f"{p.get('displayName') or '(no name)'}"]
    if p.get('email'):
        lines.append(f"  email:    {p['email']}")
    if p.get('jobTitle'):
        lines.append(f"  title:    {p['jobTitle']}")
    if p.get('department'):
        lines.append(f"  dept:     {p['department']}")
    if p.get('companyName'):
        lines.append(f"  company:  {p['companyName']}")
    if p.get('officeLocation'):
        lines.append(f"  office:   {p['officeLocation']}")
    if p.get('mobilePhone'):
        lines.append(f"  mobile:   {p['mobilePhone']}")
    bp = p.get('businessPhones') or []
    if bp:
        lines.append(f"  phones:   {', '.join(bp)}")
    if p.get('id'):
        lines.append(f"  id:       {p['id']}")
    return '\n'.join(lines)
