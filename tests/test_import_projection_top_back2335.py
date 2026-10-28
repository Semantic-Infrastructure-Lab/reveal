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
def test_unapplied_top_retains_existing_diagnostic(project, view):
    response = _run_reveal_direct(f'imports://{project}?{view}top=1', '--format', 'json')
    assert response.returncode == 0, response.stderr
    assert json.loads(response.stdout)['contract_version']
    assert "query param 'top' has no effect" in response.stderr


def test_fan_in_top_changes_rows_without_unread_diagnostic(project):
    response = _run_reveal_direct(f'imports://{project}?rank=fan-in&top=1', '--format', 'json')
    assert response.returncode == 0, response.stderr
    answer = json.loads(response.stdout)
    assert len(answer['entries']) == 1 and answer['total'] == 2
    assert answer['entries'][0]['file'] == 'bb.py'
    assert 'has no effect' not in response.stderr
