"""A page changes rows, never aggregates over the filtered statistics population."""
import json

import pytest

from conftest import _run_reveal_direct
from reveal.api import query
from reveal import mcp_server


@pytest.fixture
def project(tmp_path):
    for i in range(4):
        (tmp_path / f'f{i}.py').write_text(
            f'def f{i}(x):\n' + ''.join('    if x: x -= 1\n' for _ in range(i)) + '    return x\n', encoding='utf-8')
    return tmp_path


def ask(project, controls):
    return query(f'metrics://{project.as_posix()}?{controls}')


@pytest.mark.parametrize('controls', ['limit=1', 'limit=2', 'limit=2&offset=1', 'limit=0&offset=2',
                                     'limit=1&sort=-lines', 'limit=1&summary_only=true'])
def test_paging_preserves_whole_summary(project, controls):
    whole = ask(project, 'limit=0')
    page = ask(project, controls)
    assert whole['summary']['total_files'] == 4
    assert whole['summary']['total_functions'] == 4
    assert page['summary'] == whole['summary']
    if 'summary_only' in controls:
        assert 'files' not in page
    else:
        assert len(page['files']) < 4


@pytest.mark.parametrize('filter_', ['min_lines=3', 'lines>2'])
def test_filters_change_population_before_aggregation(project, filter_):
    whole = ask(project, filter_ + '&limit=0')
    page = ask(project, filter_ + '&limit=1&offset=1&sort=-lines')
    assert whole['summary']['total_files'] == 3
    assert page['summary'] == whole['summary']
    assert len(page['files']) == 1
    assert page['population'] == {'summary': 'filtered_analyzed_files', 'analyzed_files': 4,
                                  'filtered_files': 3, 'displayed_files': 1}
    assert page['total_matches'] == 3 and page['displayed_results'] == 1


def test_uri_generated_cli_and_mcp_have_same_aggregates(project):
    expected = ask(project, 'limit=0')['summary']
    for argv in [('metrics', str(project), '--limit', '1'),
                 (f'metrics://{project.as_posix()}?limit=1',)]:
        result = _run_reveal_direct(*argv, '--format', 'json')
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)['summary'] == expected
    result = json.loads(mcp_server.reveal_query(f'metrics://{project.as_posix()}?limit=1', provenance=True))
    assert result['summary'] == expected
