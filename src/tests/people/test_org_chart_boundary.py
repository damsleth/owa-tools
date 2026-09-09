import json

import pytest

from owa_core.errors import NetworkError, NotFoundError
from owa_people import cli


@pytest.mark.parametrize('levels', [0, 1])
def test_org_chart_manager_404_stops_chain(monkeypatch, capsys, levels):
    def get(base, path, token, **kwargs):
        if path.endswith('/manager'):
            if levels and path == 'users/person/manager':
                return {'id':'boss','displayName':'Boss'}
            raise NotFoundError('no manager')
        if path.endswith('/directReports'):
            return {'value':[{'id':'report'}]}
        return {'id':'person'}
    monkeypatch.setattr(cli.api_mod, 'api_get', get)
    assert cli.cmd_org_chart(['--depth','3'], {}, 'fake','https://example.invalid') == 0
    result = json.loads(capsys.readouterr().out)
    assert len(result['managers']) == levels
    assert result['directReports'][0]['id'] == 'report'


def test_org_chart_does_not_swallow_network_failure(monkeypatch):
    def get(base, path, token, **kwargs):
        if path.endswith('/manager'):
            raise NetworkError('failed')
        return {'id':'person'}
    monkeypatch.setattr(cli.api_mod, 'api_get', get)
    with pytest.raises(NetworkError):
        cli.cmd_org_chart([], {}, 'fake','https://example.invalid')
