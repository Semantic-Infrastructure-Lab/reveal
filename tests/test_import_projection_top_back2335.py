"""Building metadata must not mark an unapplied ranking parameter as consumed."""
import json

import pytest

from conftest import _run_reveal_direct

pytestmark = pytest.mark.component


@pytest.fixture
def project(tmp_path):
    (tmp_path / 'a.py').write_text('import bb\n', encoding='utf-8')
    (tmp_path / 'bb.py').write_text('def value():\n    return 1\n', encoding='utf-8')
    return tmp_path


@pytest.mark.parametrize('view', ['', 'unused&', 'circular&'])
@pytest.mark.parametrize('output_format', ['text', 'json'])
def test_unapplied_top_retains_existing_diagnostic(project, view, output_format):
    response = _run_reveal_direct(f'imports://{project}?{view}top=1', '--format', output_format)
    assert response.returncode == 0, response.stderr
    if output_format == 'json':
        answer = json.loads(response.stdout)
        assert answer['contract_version']
        warnings = [w for w in answer['meta']['warnings'] if w['type'] == 'unused_query_param']
        assert [(w['code'], w['fields']) for w in warnings] == [('unused_query_param', ['top'])]
        assert 'has no effect' not in response.stderr
    else:
        assert response.stderr.count("query param 'top' has no effect") == 1


def test_fan_in_top_changes_rows_without_unread_diagnostic(project):
    response = _run_reveal_direct(f'imports://{project}?rank=fan-in&top=1', '--format', 'json')
    assert response.returncode == 0, response.stderr
    answer = json.loads(response.stdout)
    assert len(answer['entries']) == 1 and answer['total'] == 2
    assert answer['entries'][0]['file'] == 'bb.py'
    assert not [w for w in answer.get('meta', {}).get('warnings', [])
                if w['type'] == 'unused_query_param' and 'top' in w['fields']]
    assert 'has no effect' not in response.stderr
