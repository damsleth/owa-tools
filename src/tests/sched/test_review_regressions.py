import json

import pytest

from owa_core.errors import ConflictError, UsageError
from owa_sched import cli, schedule


def attendee(**updates):
    raw = {
        'scheduleId': 'a@example.invalid', 'scheduleItems': [],
        'workingHours': {'daysOfWeek':['monday'], 'startTime':'09:00:00', 'endTime':'17:00:00',
                         'timeZone':{'name':'Pacific Standard Time'}},
    }
    raw.update(updates)
    return raw


@pytest.mark.parametrize('mode', [[], ['--agent'], ['--profile', 'a', '--profile', 'b']])
def test_availability_real_normalizer_is_json_safe(monkeypatch, capsys, mode):
    monkeypatch.setattr(cli.config_mod, 'load_config', lambda: {})
    monkeypatch.setattr(cli.auth_mod, 'setup_auth', lambda *a, **k: ('fake','https://example.invalid'))

    def post(*args, **kwargs):
        assert kwargs['extra_headers']['Prefer'] == 'outlook.timezone="UTC"'
        return {'value':[attendee()]}

    monkeypatch.setattr(cli.api_mod, 'api_post', post)
    assert cli.main(['availability', '--who', 'a@example.invalid', '--date', '2026-09-07', '--tz', 'UTC', *mode]) == 0
    result = json.loads(capsys.readouterr().out)
    rows = result['results'][0]['data'] if '--profile' in mode else result['data'] if '--agent' in mode else result
    assert rows[0]['workingHours']['days'] == [0]
    assert rows[0]['workingHours']['start'] == '09:00:00'
    assert rows[0]['workingHours']['timeZone'] == {'name':'Pacific Standard Time'}


@pytest.mark.parametrize('raw', [attendee(error={'message':'unavailable'}), attendee(workingHours={'startTime':'invalid'})])
def test_unknown_availability_refuses_suggestions(raw):
    with pytest.raises(ConflictError):
        schedule.find_open_slots([schedule.normalize_attendee(raw)], '2026-09-07T08:00:00', '2026-09-07T17:00:00', 30)


@pytest.mark.parametrize('payload', [{'value':[]}, {'value':[attendee(error={'message':'missing'})]}])
def test_missing_requested_schedule_is_not_free(monkeypatch, payload):
    monkeypatch.setattr(cli.api_mod, 'api_post', lambda *a, **k: payload)
    with pytest.raises(ConflictError):
        cli.cmd_find_time(['--who','a@example.invalid','--date','2026-09-07'], {}, 'fake','https://example.invalid')


@pytest.mark.parametrize('busy', [{'start':'bad','end':'bad'}, {'start':'2026-09-07T12:00:00','end':'2026-09-07T11:00:00'}])
def test_malformed_busy_interval_is_unknown(busy):
    with pytest.raises(ConflictError):
        schedule.find_open_slots([{'busy':[busy]}], '2026-09-07T08:00:00', '2026-09-07T17:00:00', 30)


@pytest.mark.parametrize('day,start', [('2026-09-07','16:00:00'), ('2026-01-05','17:00:00')])
def test_working_hours_convert_timezone_with_dst(day, start):
    rows = [schedule.normalize_attendee(attendee())]
    slots = schedule.find_open_slots(rows, f'{day}T08:00:00', f'{day}T20:00:00', 60, timezone='UTC')
    assert slots[0][0] == f'{day}T{start}'


def test_working_day_uses_attendee_date():
    # Tuesday UTC is still Monday in California.
    rows = [schedule.normalize_attendee(attendee(workingHours={
        'daysOfWeek':['monday'], 'startTime':'16:00:00','endTime':'18:00:00',
        'timeZone':{'name':'Pacific Standard Time'},
    }))]
    assert schedule.find_open_slots(rows, '2026-09-08T00:00:00','2026-09-08T02:00:00',60) == [
        ('2026-09-08T00:00:00','2026-09-08T01:00:00')]


def test_busy_interval_timezone_conversion():
    raw = attendee(workingHours=None, scheduleItems=[{
        'status':'busy', 'start':{'dateTime':'2026-09-07T09:00:00','timeZone':'Pacific Standard Time'},
        'end':{'dateTime':'2026-09-07T10:00:00','timeZone':'Pacific Standard Time'},
    }])
    assert schedule.find_open_slots([schedule.normalize_attendee(raw)], '2026-09-07T16:00:00','2026-09-07T17:00:00',30) == []


@pytest.mark.parametrize('zone', [{'@odata.type':'#microsoft.graph.customTimeZone','name':'Custom','bias':60}, {'name':'Unknown Standard Time'}])
def test_unsupported_working_timezone_fails_explicitly(zone):
    raw = attendee()
    raw['workingHours']['timeZone'] = zone
    with pytest.raises(UsageError):
        schedule.find_open_slots([schedule.normalize_attendee(raw)], '2026-09-07T08:00:00','2026-09-07T17:00:00',30)
