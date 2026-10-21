"""Overview validates required producer evidence before reducing child answers."""
import copy
from unittest.mock import patch

import pytest

from reveal.adapters.ast import AstAdapter
from reveal.adapters.git import GitAdapter
from reveal.adapters.imports import ImportsAdapter
from reveal.adapters.overview import OverviewAdapter
from reveal.adapters.stats import MetricsAdapter


@pytest.fixture
def project(tmp_path):
    (tmp_path/'a.py').write_text('import os\ndef f(): return 1\n', encoding='utf-8')
    return tmp_path


def errors(result):
    return result.get('meta', {}).get('errors', [])


@pytest.mark.parametrize('kind', ['empty', 'summary', 'boolean_count', 'missing_average',
                                 'files', 'count_mismatch', 'hotspots', 'quality'])
def test_malformed_stats_is_attributed_before_projection(project, kind):
    data = MetricsAdapter(str(project), 'hotspots=true').get_structure()
    if kind == 'empty':
        data = {}
    elif kind == 'summary':
        data['summary'] = {}
    elif kind == 'boolean_count':
        data['summary']['total_files'] = True
    elif kind == 'missing_average':
        data['summary'].pop('avg_quality_score')
    elif kind == 'files':
        data['files'] = [None]
    elif kind == 'count_mismatch':
        data['files'] = []
    elif kind == 'hotspots':
        data['hotspots'] = None
    else:
        data['hotspots'] = [{'file': 'a.py', 'quality_score': 'unknown', 'issues': []}]
    with patch.object(MetricsAdapter, 'get_structure', return_value=data):
        result = OverviewAdapter(str(project), 'no_git=true').get_structure()
    assert any(e['code'] == 'E_COMPOSE' and 'MetricsAdapter' in e['message'] for e in errors(result))


@pytest.mark.parametrize('kind', ['empty', 'results', 'missing_count', 'boolean_count',
                                 'displayed_mismatch', 'total_less', 'complexity'])
def test_malformed_ast_is_attributed_before_projection(project, kind):
    data = AstAdapter(str(project), 'complexity>9&limit=5').get_structure()
    if kind == 'empty':
        data = {}
    elif kind == 'results':
        data['results'] = [None]
    elif kind == 'missing_count':
        data.pop('total_files')
    elif kind == 'boolean_count':
        data['total_results'] = False
    elif kind == 'displayed_mismatch':
        data['displayed_results'] = 1
    elif kind == 'total_less':
        data.update(total_results=0, displayed_results=1,
                    results=[{'file': 'a.py', 'name': 'f', 'complexity': 12}])
    else:
        data.update(total_results=1, displayed_results=1,
                    results=[{'file': 'a.py', 'name': 'f', 'complexity': 'unknown'}])
    with patch.object(AstAdapter, 'get_structure', return_value=data):
        result = OverviewAdapter(str(project), 'no_git=true').get_structure()
    assert any(e['code'] == 'E_COMPOSE' and 'AstAdapter' in e['message'] for e in errors(result))


@pytest.mark.parametrize('kind', ['empty', 'boolean_count', 'negative', 'languages', 'mismatch'])
def test_malformed_scope_is_attributed(project, kind):
    from reveal.capabilities import scope_dict_for_path
    data = scope_dict_for_path(project)
    if kind == 'empty':
        data = {}
    elif kind == 'boolean_count':
        data['total_code_files'] = True
    elif kind == 'negative':
        data['skipped_dirs'] = -1
    elif kind == 'languages':
        data['languages'] = [None]
    else:
        data['total_code_files'] += 1
    with patch('reveal.adapters.overview.scope_dict_for_path', return_value=data):
        result = OverviewAdapter(str(project), 'no_git=true').get_structure()
    assert any(e['code'] == 'E_COMPOSE' and 'scope_dict_for_path' in e['message'] for e in errors(result))


@pytest.mark.parametrize('owner', ['_format_fan_in', '_format_entrypoints', '_format_components', '_format_circular'])
@pytest.mark.parametrize('kind', ['empty', 'malformed'])
def test_malformed_private_import_projection_is_attributed(project, owner, kind):
    key = 'components' if owner == '_format_components' else 'count' if owner == '_format_circular' else 'entries'
    data = {} if kind == 'empty' else {key: True if key == 'count' else [None]}
    with patch.object(ImportsAdapter, owner, return_value=data):
        result = OverviewAdapter(str(project), 'no_git=true').get_structure()
    assert any(e['code'] == 'E_COMPOSE' and 'ImportsAdapter' in e['message'] for e in errors(result))


@pytest.mark.parametrize('kind', ['empty', 'missing_count', 'boolean_count', 'lost_exceeds',
                                 'paths', 'cause', 'unsupported', 'missing_unsupported'])
def test_malformed_import_metadata_is_attributed(project, kind):
    original = ImportsAdapter.get_metadata
    def malformed(self):
        data = copy.deepcopy(original(self))
        if kind == 'empty':
            return {}
        if kind == 'missing_count':
            data.pop('files_failed_count')
        elif kind == 'boolean_count':
            data['files_failed_count'] = False
        elif kind == 'lost_exceeds':
            data.update(files_lost_count=1, files_lost=['a.py'])
        elif kind == 'paths':
            data['files_failed'] = [None]
        elif kind == 'cause':
            data['extraction_diagnostics'] = []
        elif kind == 'missing_unsupported':
            data.pop('unsupported_extensions')
        else:
            data['unsupported_extensions'] = []
        return data
    with patch.object(ImportsAdapter, 'get_metadata', malformed):
        result = OverviewAdapter(str(project), 'no_git=true').get_structure()
    assert any(e['code'] == 'E_COMPOSE' and 'ImportsAdapter' in e['message'] for e in errors(result))


@pytest.mark.parametrize('owner', [MetricsAdapter, AstAdapter])
def test_existing_compose_failure_is_not_duplicated(project, owner):
    with patch.object(owner, 'get_structure', side_effect=OSError('exact child failure')):
        result = OverviewAdapter(str(project), 'no_git=true').get_structure()
    failure, = errors(result)
    assert failure['code'] == 'E_COMPOSE' and 'exact child failure' in failure['message']


@pytest.mark.parametrize('metadata', [{}, {'type': 'git_repository'}, {'path': None}])
def test_absent_git_root_is_legitimate_optional_skip(project, metadata):
    with patch.object(GitAdapter, 'get_metadata', return_value=metadata), \
            patch('reveal.adapters.overview._run_git_log') as history:
        result = OverviewAdapter(str(project)).get_structure()
    history.assert_not_called()
    assert not errors(result) and result['git_log'] == []


def test_nonmapping_git_metadata_is_attributed(project):
    with patch.object(GitAdapter, 'get_metadata', return_value=[]):
        result = OverviewAdapter(str(project)).get_structure()
    failure, = errors(result)
    assert failure['code'] == 'E_COMPOSE' and 'git_root' in failure['message']


@pytest.mark.parametrize('kind', ['empty', 'missing', 'malformed'])
def test_applicable_git_history_requires_its_actual_list(project, kind):
    data = {} if kind == 'empty' else {'history': None} if kind == 'missing' else {'history': [None]}
    with patch.object(GitAdapter, 'get_metadata', return_value={'path': str(project)}), \
            patch.object(GitAdapter, 'get_structure', return_value=data):
        result = OverviewAdapter(str(project)).get_structure()
    assert any(e['code'] == 'E_COMPOSE' and 'GitAdapter' in e['message'] for e in errors(result))
