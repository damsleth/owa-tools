"""owa-kova: duty parsing, profile resolution, CLI. No network, no real data."""
import json

import pytest

from owa_core.auth import BrokerProfile
from owa_core.errors import AuthExpiredError, UsageError
from owa_kova import cli, schedule, session

FRAGMENT = """<div class="MonthHeader">desember 2026</div><div class="WeekHeader">Uke 52 - 2026</div>
<div class="OpenDuty Me Full" CrewRef="c1" EventRef="e1" ReportName="Nyttårsvakt" Title="">
<div class="EventInfo"><div class="Event" Title="Sentrum &amp; havna">Nyttårsvakt</div>
<div class="Duty" Title="Oppmøte depot">Vakt sentrum</div>
<div class="Date"><b>Fra:</b> tor. 31.12, kl. 20:00<br/><b>Til:</b> fre. 01.01, kl. 03:00</div></div>
<table class="CrewTable"><tr><th></th></tr>
<tr class="PersonRow"><td class="Role">Mannskap</td><td class="Name">Nordmann, Kari</td><td>+4700000000</td><td></td></tr>
<tr class="PersonRow"><td class="Role">Vaktleder</td><td class="MyName">Me, Myself</td><td>+4711111111</td><td></td></tr>
</table></div>
<div class="OpenDuty Locked" CrewRef="c2" EventRef="e2" ReportName="Korpskveld"><div class="EventInfo">
<div class="Event">Korpskveld</div><div class="Duty">Øvelse</div><div class="Date">ons. 30.12, kl. 18:00 - 21:00</div></div>
<table class="CrewTable"><tr class="PersonRow"><td class="Role">Deltaker</td><td class="Name">Nordmann, Ola</td></tr></table></div>"""


def test_parse_duties_reads_names_flags_and_times():
    first, second = schedule.parse_duties(FRAGMENT)
    assert first['event'] == 'Nyttårsvakt' and first['duty'] == 'Vakt sentrum'
    assert (first['start'], first['end']) == ('2026-12-31T20:00', '2027-01-01T03:00')
    assert (first['mine'], first['full'], first['locked'], first['my_role']) == (True, True, False, 'Vaktleder')
    assert first['event_info'] == 'Sentrum & havna'
    assert (second['start'], second['end']) == ('2026-12-30T18:00', '2026-12-30T21:00')
    assert (second['mine'], second['locked'], second['my_role']) == (False, True, None)


def test_parse_duties_never_carries_other_members():
    """The crew table holds other members' names and phone numbers."""
    out = json.dumps(schedule.parse_duties(FRAGMENT), ensure_ascii=False)
    for leak in ('Nordmann', '+4700000000', 'Me, Myself', '+4711111111'):
        assert leak not in out


def test_same_day_shift_past_midnight_ends_next_day():
    assert schedule.parse_times('lør. 31.10, kl. 22:00 - 02:00', 2026) == ('2026-10-31T22:00', '2026-11-01T02:00')
    assert schedule.parse_times('ukjent', 2026) == (None, None)


def _profiles(monkeypatch, rows):
    monkeypatch.setattr(session, 'get_profiles', lambda **kw: rows)


def test_resolve_sidecar(monkeypatch):
    brkh = BrokerProfile('brkh', False, True, True, services=('owa', 'kova'), edge_dir='/x/brkh/edge-profile')
    swon = BrokerProfile('swon', True, True, True)
    _profiles(monkeypatch, [swon, brkh])
    assert session.resolve_sidecar() == ('brkh', session.Path('/x/brkh/edge-profile'))
    with pytest.raises(AuthExpiredError, match='not signed in to Kova'):
        session.resolve_sidecar('swon')
    _profiles(monkeypatch, [swon])
    with pytest.raises(UsageError, match='no profile has Kova'):
        session.resolve_sidecar()


def test_schedule_command_asks_for_mine_from_the_given_date(monkeypatch, capsys):
    seen = []
    monkeypatch.setattr(session, 'fetch_json', lambda paths, **kw: seen.extend(paths) or [FRAGMENT])
    assert cli.main(['schedule', '--from', '2026-12-01']) == 0
    assert seen == ['/api/default/GetOpenDuties?pStartDate=2026-12-01&pOnlyMine=true']
    assert len(json.loads(capsys.readouterr().out)) == 2
    seen.clear()
    assert cli.main(['schedule', '--open']) == 0
    assert seen == ['/api/default/GetOpenDuties?pStartDate=&pOnlyMine=false']


def test_schedule_rejects_a_bad_date(capsys):
    assert cli.main(['schedule', '--from', 'tomorrow']) != 0
