"""Architecture guardrails for shared release contracts."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIRS = [
    'owa',
    'owa_core',
    'owa_cal',
    'owa_mail',
    'owa_graph',
    'owa_doctor',
    'owa_people',
    'owa_sched',
    'owa_drive',
]


def _runtime_files():
    for package in RUNTIME_DIRS:
        yield from (ROOT / package).rglob('*.py')


def test_urllib_http_usage_stays_in_core_http():
    offenders = []
    for path in _runtime_files():
        rel = path.relative_to(ROOT)
        if rel.as_posix() == 'owa_core/http.py':
            continue
        text = path.read_text()
        if 'urllib.request' in text or 'urllib.error' in text:
            offenders.append(str(rel))
    assert offenders == []


def test_owa_piggy_json_broker_calls_stay_in_core_auth():
    offenders = []
    needles = (
        "['owa-piggy', 'token'",
        '["owa-piggy", "token"',
        "['owa-piggy', 'profiles'",
        '["owa-piggy", "profiles"',
    )
    for path in _runtime_files():
        rel = path.relative_to(ROOT)
        if rel.as_posix() == 'owa_core/auth.py':
            continue
        text = path.read_text()
        if any(needle in text for needle in needles):
            offenders.append(str(rel))
    assert offenders == []


def test_legacy_broker_shims_do_not_return():
    forbidden = (
        'run_piggy_token',
        'setup_or_exit',
        'check_owa_piggy_version',
        '_owa_piggy_available',
        '_check_owa_piggy_version',
    )
    offenders = []
    for path in _runtime_files():
        text = path.read_text()
        found = [name for name in forbidden if name in text]
        if found:
            offenders.append(f'{path.relative_to(ROOT)}: {", ".join(found)}')
    assert offenders == []
