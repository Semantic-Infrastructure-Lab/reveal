"""Required census and import evidence is validated before map presentation."""
from copy import deepcopy
from unittest.mock import patch

import pytest

from reveal.adapters.overview import OverviewAdapter
from reveal.analyzers.imports.views import ImportView
from reveal.capabilities import scope_dict_for_path
from reveal.utils.results import AnalysisCompleteness


@pytest.fixture
def project(tmp_path):
    (tmp_path / 'a.py').write_text('import os\n', encoding='utf-8')
    return tmp_path


@pytest.mark.parametrize('kind', ['empty', 'boolean_count', 'languages', 'mismatch'])
def test_malformed_census_is_required_failure(project, kind):
    data = scope_dict_for_path(project)
    if kind == 'empty':
        data = {}
    elif kind == 'boolean_count':
        data['total_code_files'] = True
    elif kind == 'languages':
        data['languages'] = [None]
    else:
        data['total_code_files'] += 1
    with patch('reveal.adapters.overview.scope_dict_for_path', return_value=data):
        result = OverviewAdapter(str(project)).get_structure()
    assert result['map_status'] == 'failed'
    assert any('scope_dict_for_path' in e['message'] for e in result['meta']['errors'])
    assert OverviewAdapter.execution_facts(result).completeness is AnalysisCompleteness.FAILED


@pytest.mark.parametrize('owner', ['fan_in', 'entrypoints', 'components', 'circular'])
@pytest.mark.parametrize('data', [{}, {'entries': [None]}])
def test_malformed_import_projection_is_attributed(project, owner, data):
    with patch.object(ImportView, owner, return_value=data):
        result = OverviewAdapter(str(project)).get_structure()
    assert result['map_status'] == 'failed'
    assert any('ImportsAdapter' in e['message'] for e in result['meta']['errors'])


@pytest.mark.parametrize('kind', ['missing_count', 'boolean_count', 'lost_exceeds', 'paths', 'cause',
                                 'unsupported', 'missing_unsupported', 'scanned_files', 'scan_budget'])
def test_malformed_import_metadata_is_attributed(project, kind):
    original = ImportView.get_metadata
    def malformed(self):
        data = deepcopy(original(self))
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
        elif kind in ('scanned_files', 'scan_budget'):
            data.pop(kind)
        else:
            data['unsupported_extensions'] = []
        return data
    with patch.object(ImportView, 'get_metadata', malformed):
        result = OverviewAdapter(str(project)).get_structure()
    assert result['map_status'] == 'failed'
    assert any('ImportsAdapter' in e['message'] for e in result['meta']['errors'])
