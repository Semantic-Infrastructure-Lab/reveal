"""BACK-2599: patches' text (every view, and the retired testability that shares the pressure renderer) prints its
standing caveats and a selected project's test-path basis as the one Rules: pointer, and keeps what is specific to the
request visible: a basis with no project boundary, the scope count, and failure or incomplete-input warnings."""
from argparse import Namespace

import pytest

from reveal.adapters.patches import PatchesAdapter, PatchesRenderer
from reveal.cli.routing.uri import _emit_result

pytestmark = pytest.mark.component

_ADVISORY = 'Patch pressure is advisory; mocking external boundaries can be correct.'
_BEST_EFFORT = 'Static target resolution is best-effort.'
_FALLBACK = {'rule': 'is_test_path', 'files_scanned': 1, 'anchor': '.', 'source': 'scan_root_fallback',
             'include_anchor_name': True, 'basis': 'scan-root name and relative paths; project boundary unknown',
             'suite_roots': ['.']}


def _result(tmp_path, query=''):
    (tmp_path / 'tests').mkdir(exist_ok=True)
    (tmp_path / 'tests' / 'test_demo.py').write_text(
        'from unittest.mock import patch\n@patch("service.call")\ndef test_call(mock):\n    pass\n', encoding='utf-8')
    return PatchesAdapter(str(tmp_path), query).get_structure()


def _emitted(result, capsys):
    _emit_result(result, Namespace(format='text', also_json=None), 'patches', PatchesRenderer.render_structure)
    return capsys.readouterr().out


@pytest.mark.parametrize('query,standing', [('', [_ADVISORY]), ('view=pressure', [_BEST_EFFORT, _ADVISORY])])
def test_standing_caveats_are_one_pointer_and_request_warnings_stay(tmp_path, capsys, query, standing):
    result = _result(tmp_path, query)
    assert [w['message'] for w in result['meta']['warnings']] == standing  # the premise: the JSON carries them
    result['meta']['warnings'].append({'type': 'analysis_failed', 'message': '1 file failed to parse'})
    result['meta']['errors'] = [{'message': 'recorded partial scan'}]
    text = _emitted(result, capsys)
    rules = [line.strip() for line in text.splitlines() if line.strip().startswith('Rules: ')]
    assert len(rules) == 1 and rules[0].endswith('meta.warnings)'), rules
    for sentence in standing:
        assert sentence not in text
    assert text.count('1 file failed to parse') == 1  # request-specific: stays visible, once
    assert text.count('recorded partial scan') == 1


@pytest.mark.parametrize('query', ['', 'view=pressure'])
def test_basis_with_no_project_boundary_stays_visible(tmp_path, capsys, query):
    """Control: with no project boundary the scan root's own name counts as a test path, a fact of this request, so
    the basis stays beside the pointer (as imports keeps it, BACK-2685); a selected project's basis does not."""
    result = _result(tmp_path, query)
    result['test_scope'] = dict(_FALLBACK)
    text = _emitted(result, capsys)
    assert ('Test scope: is_test_path (1 test files scanned); scan-root name and relative paths; '
            'project boundary unknown (anchor: .)') in text
    result['test_scope'] = dict(_FALLBACK, source='project', include_anchor_name=False,
                                basis='paths relative to the selected project')
    text = _emitted(result, capsys)
    assert 'Test scope: is_test_path (1 test files scanned)' in text
    assert 'paths relative to the selected project' not in text
    assert 'Rules: --format json (test_scope.basis, meta.warnings)' in text


@pytest.mark.parametrize('query', ['', 'view=pressure'])
@pytest.mark.parametrize('selectors,suffix', [(['suite'], 'conventional names plus declared additional paths'),
                                              (['.'], 'WHOLE SCOPE selected by explicit .')])
def test_declared_test_layout_basis_stays_visible(tmp_path, capsys, query, selectors, suffix):
    """Control: a declared test_layout changes what counts as a test (the whole scope with '.'), so its basis stays."""
    result = _result(tmp_path, query)
    basis = f'paths relative to the selected project; {suffix}'
    result['test_scope'] = dict(_FALLBACK, source='project', include_anchor_name=False, basis=basis,
                                additional_paths=selectors, whole_scope='.' in selectors)
    text = _emitted(result, capsys)
    assert f'Test scope: is_test_path (1 test files scanned); {basis} (anchor: .)' in text
