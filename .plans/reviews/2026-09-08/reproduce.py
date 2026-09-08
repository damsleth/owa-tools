"""Offline review probes: assertions document defects in the reviewed checkout."""
import contextlib
import io
import json
from types import SimpleNamespace
from unittest.mock import patch

from owa_core import http, modes, secrets
from owa_core.errors import NetworkError
from owa_drive import cli as drive
from owa_sched import cli as sched, schedule
from owa_swodp import service as swodp
from owa_teams import api as teams

results = []
def probe(name, fn):
    fn()
    results.append(name)
    print('CONFIRMED:', name)

def drive_fail_open():
    with patch.object(drive.http_mod, 'request', side_effect=NetworkError('offline')), patch.object(drive, '_upload_one', return_value=('uploaded', {'id': 'fake'})) as upload, contextlib.redirect_stdout(io.StringIO()):
        assert drive.cmd_put(['local.txt', '/existing.txt'], {}, 'fake', 'https://example.invalid') == 0
        upload.assert_called_once()
probe('R1 Drive uploads after failed existence preflight without --force', drive_fail_open)

def schedule_json():
    raw = {'scheduleId': 'a@example.invalid', 'workingHours': {'daysOfWeek': ['monday'], 'startTime': '09:00:00', 'endTime': '17:00:00'}}
    with patch.object(sched.api_mod, 'api_post', return_value={'value': [raw]}):
        try:
            sched.cmd_availability(['--who', 'a@example.invalid', '--date', '2026-09-07'], {}, 'fake', 'https://example.invalid')
        except TypeError as exc:
            assert 'not JSON serializable' in str(exc)
        else:
            raise AssertionError('expected serialization failure')
probe('R2 Availability crashes serializing workingHours', schedule_json)

def schedule_unknown():
    raw = {'scheduleId': 'a@example.invalid', 'error': {'message': 'mailbox inaccessible'}}
    with patch.object(sched.api_mod, 'api_post', return_value={'value': [raw]}), contextlib.redirect_stdout(io.StringIO()) as out:
        assert sched.cmd_find_time(['--who', 'a@example.invalid', '--date', '2026-09-07'], {}, 'fake', 'https://example.invalid') == 0
    assert json.loads(out.getvalue())
probe('R3 Inaccessible attendee produces successful free slots', schedule_unknown)

def body_leak():
    text = secrets.redact(json.dumps({'Body': {'Content': 'hello "PRIVATE_REMAINDER"'}}))
    assert 'PRIVATE_REMAINDER' in text
probe('R4 Escaped quotes bypass body redaction', body_leak)

def error_leak():
    fake_jwt = '.'.join(['A' * 12, 'B' * 12, 'C' * 12])
    def dispatch(argv):
        raise NetworkError('failure ' + fake_jwt)
    with contextlib.redirect_stdout(io.StringIO()) as out:
        assert modes.run_with_output_modes('fake', ['get', '--profile', 'a', '--profile', 'b'], dispatch) == 1
    assert fake_jwt in out.getvalue()
probe('R5 Multi-profile errors bypass secret redaction', error_leak)

def invalid_output():
    def dispatch(argv):
        print('not json')
        return 0
    with contextlib.redirect_stdout(io.StringIO()) as out:
        assert modes.run_with_output_modes('fake', ['get', '--profile', 'a', '--profile', 'b'], dispatch) == 0
    assert all(not r['ok'] for r in json.loads(out.getvalue())['results'])
probe('R6 Multi-profile non-JSON failures exit zero', invalid_output)

def binary_alias():
    with patch.object(drive.config_mod, 'load_config', return_value={}), patch.object(drive.auth_mod, 'setup_auth', return_value=('fake', 'https://example.invalid')), patch.object(drive.api_mod, 'api_get_binary', return_value=b'fake'):
        with contextlib.redirect_stdout(io.StringIO()):
            try:
                drive.main(['download', '/fake', '--agent'])
            except AttributeError as exc:
                assert 'buffer' in str(exc)
            else:
                raise AssertionError('expected bypass')
probe('R7 Download alias bypasses agent binary guard', binary_alias)

def timeout():
    def failing(*a, **k):
        raise TimeoutError('timed out')
    try:
        http.request('GET', 'https://example.invalid', token='fake', urlopen=failing)
    except TimeoutError:
        return
    raise AssertionError('expected untyped timeout')
probe('R8 HTTP timeout escapes typed network errors', timeout)

def debug_url():
    with contextlib.redirect_stderr(io.StringIO()) as out:
        try:
            http.request_unauthenticated('PUT', 'https://example.invalid/upload?sig=FAKE_SIGNED_CAPABILITY', debug=True, urlopen=lambda *a, **k: (_ for _ in ()).throw(TimeoutError()))
        except TimeoutError:
            pass
    assert 'FAKE_SIGNED_CAPABILITY' in out.getvalue()
probe('R9 Signed upload URL printed verbatim by debug', debug_url)

def truncation():
    response = http.Response(200, {}, {'value': [{'id': 1}]}, b'', next_link='https://example.invalid/next')
    with patch.object(http, 'request', return_value=response):
        rows, truncated = teams.graph_collect('https://example.invalid', 'me/chats', 'fake', max_pages=1)
    assert rows == [{'id': 1}] and truncated is False
probe('R10 Teams page-cap truncation reported as complete', truncation)

def split_delete():
    calls=[]
    def request(session, method, table, **kwargs):
        calls.append((method, table))
        if method == 'GET' and table == 'time_card':
            return [{'sys_id': 'a'*32, 'task.number': 'T12345', 'state': 'Pending'}]
        if method == 'GET' and table == 'task':
            return []
        return {}
    row={'taskNumber':'T12345', 'days':[1,0,0,0,0,0,0], 'description':'fake', 'split':True}
    with patch.object(swodp.api, 'request', side_effect=request):
        output=swodp.write_week(SimpleNamespace(user='fake'), '2026-09-07', [row])
    assert calls.index(('DELETE','time_card')) < calls.index(('GET','task'))
    assert [r['action'] for r in output] == ['deleted','skipped']
probe('R11 SWODP split deletes originals before resolving replacement task', split_delete)

def org_chart_top():
    from owa_people import cli as people
    from owa_core.errors import NotFoundError
    with patch.object(people.api_mod, 'api_get', side_effect=[{'id':'fake'}, NotFoundError('no manager')]):
        try:
            people.cmd_org_chart([], {}, 'fake', 'https://example.invalid')
        except NotFoundError:
            return
        raise AssertionError('expected premature failure')
probe('R12 Org chart aborts at a valid top-of-chain manager 404', org_chart_top)

print(f'{len(results)} offline defect reproductions confirmed; no broker or service calls.')
