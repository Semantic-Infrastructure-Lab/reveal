"""Surface reports observations and limitations without unmeasured confidence."""
import copy

import pytest

from reveal.adapters import surface
from reveal.rendering.adapters.surface import surface_text
from reveal.utils.results import AnalysisCompleteness, ResultBuilder
from test_surface_traversal_loss_back2028 import _project, fault

pytestmark = pytest.mark.component


def _without_estimates(answer):
    answer = copy.deepcopy(answer)
    for key in ('meta', '_meta'):
        answer.get(key, {}).pop('confidence', None)
    return answer


def _absent(answer):
    assert all('confidence' not in answer[key] for key in ('meta', '_meta')), answer


@pytest.mark.parametrize('case,filename,source,total,warning,state', [
    ('healthy', 'app.py', 'import os\nx=os.getenv("VISIBLE")\n', 1, None, 'complete'),
    ('empty', 'app.py', 'x=1\n', 0, None, 'complete'),
    ('unsupported', 'app.lua', 'local x=1\n', 0, 'W-SURFACE-1', 'complete'),
    ('unparsed', 'app.py', 'def broken(:\n', 0, 'W-SURFACE-2', 'incomplete'),
    ('recovered', 'app.ts', 'function f( {\n const x=1;\n}}}\n', 0, 'W-SURFACE-3', 'incomplete'),
], ids=['healthy', 'empty', 'unsupported', 'unparsed', 'recovered'])
def test_actual_scan_omits_unmeasured_estimates(tmp_path, case, filename, source, total, warning, state):
    (tmp_path / filename).write_text(source, encoding='utf-8')
    raw = surface._scan_surface(tmp_path)
    answer = surface.SurfaceAdapter(str(tmp_path)).get_structure()
    assert answer['type'] == 'surface_scan' and answer['contract_version'] == '1.1'
    assert answer['source'] == str(tmp_path) and answer['total'] == total
    assert answer['scope']['total_code_files'] == answer['coverage']['total_code_files'] == 1
    assert answer['coverage']['analyzed_files'] == (0 if case == 'unsupported' else 1)
    assert answer['meta']['parse_mode'] == 'ast+tree_sitter'
    assert answer['_meta']['analysis_kind'] == 'surface-scan'
    assert answer['_meta']['known_limits'] and answer['matrix'] is not None
    assert surface.SurfaceAdapter.execution_facts(answer).completeness.value == state
    assert [w['code'] for w in answer['meta']['warnings']] == ([warning] if warning else [])
    assert answer['unparsed_files'] == ([filename] if case == 'unparsed' else [])
    assert answer['recovered_files'] == ([filename] if case == 'recovered' else [])
    if total:
        assert answer['surfaces']['env'][0]['name'] == 'VISIBLE'
    assert surface_text(answer) == surface_text(_without_estimates(answer))
    assert 'confidence' not in raw['_meta']
    _absent(answer)


@pytest.mark.parametrize('stage', ['source', 'census'])
@pytest.mark.parametrize('useful', [False, True])
def test_existing_loss_repair_reuse_and_sibling_evidence_is_preserved(tmp_path, fault, stage, useful):
    root = tmp_path / 'project'
    child = _project(root, useful=useful, hidden=useful)
    sibling = tmp_path / 'sibling'
    _project(sibling)
    adapter = surface.SurfaceAdapter(str(root))
    clean = adapter.get_structure()
    sibling_clean = surface.SurfaceAdapter(str(sibling)).get_structure()
    fault['denied'].add((stage, child.resolve()))
    answer = adapter.get_structure()
    assert len(fault['attempts']) == 1
    _absent(answer)
    assert answer['total'] == (int(useful) if stage == 'source' else 2 * int(useful))
    warning, = [w for w in answer['meta']['warnings'] if w.get('unit') == 'directories']
    assert warning['count'] == 1 and 'missing file population is unknown' in warning['message']
    assert answer['scope']['total_code_files'] == (2 if stage == 'source' else 1)
    expected = AnalysisCompleteness.INCOMPLETE if useful else AnalysisCompleteness.FAILED
    assert surface.SurfaceAdapter.execution_facts(answer).completeness is expected
    assert surface.SurfaceAdapter(str(sibling)).get_structure() == sibling_clean
    fault['denied'].clear()
    assert adapter.get_structure() == clean


def test_filter_and_source_only_keep_real_counts_and_known_limits(tmp_path):
    _project(tmp_path)
    tests = tmp_path / 'tests'
    tests.mkdir()
    (tests / 'test_app.py').write_text('import os\nx=os.getenv("TESTING")\n', encoding='utf-8')
    answer = surface.SurfaceAdapter(str(tmp_path), 'type=env&source_only=true&by=dir&depth=0').get_structure()
    assert answer['total'] == 2 and set(answer['surfaces']) == {'env'}
    assert answer['scope']['total_code_files'] == 3
    assert {row['name'] for row in answer['surfaces']['env']} == {'VISIBLE', 'HIDDEN'}
    assert 'test files excluded (--source-only)' in answer['_meta']['known_limits']
    assert sum(row['total'] for row in answer['by_dir']) == 2
    _absent(answer)


def test_shared_builder_still_accepts_optional_measured_confidence():
    answer = ResultBuilder.create('probe', '.', contract_version='1.1', confidence=0.75)
    assert answer['meta']['confidence'] == 0.75
