"""Deps retains required component proof before projecting child answers."""
import copy

import pytest

from reveal.adapters.deps import DepsAdapter, _run_base, _run_circular, _run_unused
from reveal.adapters.imports import ImportsAdapter
from reveal.utils.results import ResultBuilder, note_truncation

pytestmark = pytest.mark.component


def child(component):
    payload = {'base': {'files': {}}, 'circular': {'cycles': [], 'count': 0},
               'unused': {'unused': [], 'count': 0}}[component]
    result = ResultBuilder.create('imports', '.', data=payload)
    result['metadata'] = {'files_failed_count': 0, 'files_lost_count': 0,
                          'files_failed': [], 'files_lost': []}
    return result


def install(monkeypatch, selected=None, replacement=None):
    def produce(self, **kwargs):
        component = 'unused' if 'unused' in self._query_params else 'circular' if 'circular' in self._query_params else 'base'
        if component == selected:
            if isinstance(replacement, Exception):
                raise replacement
            return copy.deepcopy(replacement)
        return child(component)
    monkeypatch.setattr(ImportsAdapter, 'get_structure', produce)


def test_real_recovered_input_keeps_surviving_findings_and_exact_proof(tmp_path):
    (tmp_path/'a.py').write_text('import os\ndef broken(\n', encoding='utf-8')
    result = DepsAdapter(str(tmp_path)).get_structure()
    assert result['base']['metadata']['files_failed_count'] == 1
    assert result['unused']
    assert result['analysis']['complete'] is False
    assert result['analysis']['findings']['unused'] == len(result['unused'])
    for component in result['analysis']['components'].values():
        assert component['completeness'] == 'incomplete'
        assert component['files_failed_count'] == 1
        assert component['diagnostics']['extraction_diagnostics']


@pytest.mark.parametrize('component', ['base', 'circular', 'unused'])
@pytest.mark.parametrize('kind', ['raised', 'returned', 'missing', 'malformed', 'missing_proof', 'bad_count'])
def test_required_child_failure_is_not_clean(tmp_path, monkeypatch, component, kind):
    result = child(component)
    if kind == 'raised':
        result = OSError('required child inaccessible')
    elif kind == 'returned':
        result['error'] = 'required child returned failure'
    elif kind == 'missing':
        result = {}
    elif kind == 'malformed':
        result[{'base': 'files', 'circular': 'cycles', 'unused': 'unused'}[component]] = 7
    elif kind == 'missing_proof':
        result.pop('metadata')
    else:
        result['metadata']['files_failed_count'] = 'unknown'
    install(monkeypatch, component, result)
    answer = DepsAdapter(str(tmp_path)).get_structure()
    assert answer['analysis']['complete'] is False
    assert answer['analysis']['components'][component]['completeness'] == 'failed'
    assert any(e.get('component') == component for e in answer['meta']['errors'])


def test_unused_only_lost_inputs_and_diagnostic_cap_survive_projection(tmp_path, monkeypatch):
    result = child('unused')
    paths = [f'file_{n}.py' for n in range(50)]
    result['metadata'].update(files_failed_count=73, files_lost_count=73,
                              files_failed=paths, files_lost=paths,
                              extraction_diagnostics={'file_0.py': {'parse': {'status': 'unavailable', 'reason': 'worker terminated'}}})
    note_truncation(result, 'metadata.files_failed', 50, 73, 'auto_cap', hint='first 50; count exact')
    install(monkeypatch, 'unused', result)
    answer = DepsAdapter(str(tmp_path)).get_structure()
    record = answer['analysis']['components']['unused']
    assert record['completeness'] == 'incomplete'
    assert record['files_failed_count'] == record['files_lost_count'] == 73
    assert record['diagnostics']['files_failed'] == paths
    assert record['diagnostics']['files_lost'] == paths
    assert 'worker terminated' in str(record['diagnostics'])
    warning, = [w for w in answer['meta']['warnings'] if w.get('type') == 'truncated']
    assert warning['field'] == 'analysis.components.unused.diagnostics.files_failed'
    assert warning['total'] == 73 and warning['shown'] == 50
    assert 'first 50; count exact' in warning['message']
    assert warning['field'] in warning['message']


@pytest.mark.parametrize('warning', ['partial_parse', 'worker_lost', 'analysis_failed', 'parse_recovered'])
def test_explicit_child_missing_evidence_warning_is_retained(tmp_path, monkeypatch, warning):
    result = child('unused')
    result['meta'] = {'warnings': [{'type': warning, 'message': 'known missing input'}], 'errors': []}
    install(monkeypatch, 'unused', result)
    answer = DepsAdapter(str(tmp_path)).get_structure()
    assert not answer['analysis']['complete']
    assert answer['analysis']['components']['unused']['completeness'] == 'incomplete'
    assert any(w.get('type') == warning for w in answer['meta']['warnings'])


def test_child_per_file_errors_are_incomplete_not_full_failure(tmp_path, monkeypatch):
    result = child('unused')
    result['meta'] = {'errors': [{'code': 'per_file', 'message': 'retained exact cause'}]}
    install(monkeypatch, 'unused', result)
    answer = DepsAdapter(str(tmp_path)).get_structure()
    assert answer['analysis']['components']['unused']['completeness'] == 'incomplete'
    assert any(e['message'] == 'retained exact cause' for e in answer['meta']['errors'])


def test_clean_limits_unknown_warnings_and_confidence_are_not_failure(tmp_path, monkeypatch):
    result = child('unused')
    result['metadata'].update(unsupported_extensions={'.lua': 5}, unused_not_checked_extensions={'.rb': 2},
                              autoload_regime={'framework': 'Ruby on Rails'})
    result['meta'] = {'warnings': [{'type': 'custom', 'message': 'harmless'}], 'confidence': 0.0}
    install(monkeypatch, 'unused', result)
    answer = DepsAdapter(str(tmp_path)).get_structure()
    assert answer['analysis']['complete'] is True
    assert answer['meta']['confidence'] == 0.0
    assert {'type': 'custom', 'message': 'harmless'} in answer['meta']['warnings']


def test_skip_controls_remove_required_components_and_findings(tmp_path, monkeypatch):
    install(monkeypatch, 'unused', OSError('must not execute'))
    answer = DepsAdapter(str(tmp_path), 'no_unused=true&no_circular=true').get_structure()
    assert answer['skipped'] == ['circular', 'unused']
    assert list(answer['analysis']['components']) == ['base']
    assert answer['analysis']['findings'] == {}
    assert answer['analysis']['complete'] is True


def test_findings_counts_keep_all_uncapped_arrays(tmp_path, monkeypatch):
    def produce(self, **kwargs):
        component = 'unused' if 'unused' in self._query_params else 'circular' if 'circular' in self._query_params else 'base'
        result = child(component)
        if component == 'unused':
            result.update(unused=[{'file': f'f_{n}.py', 'module': 'os'} for n in range(25)], count=25)
        elif component == 'circular':
            result.update(cycles=[[f'a_{n}.py', f'b_{n}.py'] for n in range(23)], count=23)
        return result
    monkeypatch.setattr(ImportsAdapter, 'get_structure', produce)
    answer = DepsAdapter(str(tmp_path), 'top=0').get_structure()
    assert answer['analysis']['findings'] == {'circular': 23, 'unused': 25}
    assert len(answer['unused']) == 25 and len(answer['circular']['cycles']) == 23


def test_reused_adapter_clears_failed_request_evidence(tmp_path, monkeypatch):
    adapter = DepsAdapter(str(tmp_path))
    install(monkeypatch, 'unused', OSError('first request failure'))
    first = adapter.get_structure()
    assert first['analysis']['complete'] is False
    install(monkeypatch)
    second = adapter.get_structure()
    assert second['analysis']['complete'] is True
    assert all(c['completeness'] == 'complete' for c in second['analysis']['components'].values())
    assert not second.get('meta', {}).get('errors')
    assert not adapter.__dict__.get('_deps_components')


def test_empty_and_unsupported_inputs_remain_complete(tmp_path):
    empty = DepsAdapter(str(tmp_path)).get_structure()
    (tmp_path/'a.m').write_text('int value = 1;\n', encoding='utf-8')
    unsupported = DepsAdapter(str(tmp_path)).get_structure()
    assert empty['analysis']['complete'] is True
    assert unsupported['analysis']['complete'] is True
    assert unsupported['base']['metadata']['unsupported_extensions'] == {'.m': 1}


def test_existing_helper_return_shapes_remain_compatible(tmp_path, monkeypatch):
    install(monkeypatch)
    adapter = DepsAdapter(str(tmp_path))
    assert isinstance(_run_base(adapter, tmp_path), dict)
    assert isinstance(_run_circular(adapter, tmp_path), dict)
    assert _run_unused(adapter, tmp_path) == []


def test_imports_response_has_no_deps_carrier(tmp_path):
    (tmp_path/'a.py').write_text('import os\n', encoding='utf-8')
    result = ImportsAdapter(str(tmp_path)).get_structure()
    assert 'analysis' not in result
    assert 'files' in result and result['metadata']['files_failed_count'] == 0


@pytest.mark.parametrize('proof', [None, {}, {'files_failed_count': 'unknown', 'files_lost_count': 0},
                                 {'files_failed_count': 1, 'files_lost_count': 2}])
def test_invalid_count_proof_is_unknown_not_measured_zero(tmp_path, monkeypatch, proof):
    result = child('unused')
    result['metadata'] = proof
    install(monkeypatch, 'unused', result)
    record = DepsAdapter(str(tmp_path)).get_structure()['analysis']['components']['unused']
    assert record['completeness'] == 'failed'
    assert record['files_failed_count'] is None and record['files_lost_count'] is None


def test_valid_zero_count_proof_is_retained(tmp_path, monkeypatch):
    install(monkeypatch)
    record = DepsAdapter(str(tmp_path)).get_structure()['analysis']['components']['unused']
    assert record['completeness'] == 'complete'
    assert record['files_failed_count'] == record['files_lost_count'] == 0


def test_invalid_child_count_keeps_surviving_unused_entries(tmp_path, monkeypatch):
    result = child('unused')
    result.update(unused=[{'file': 'a.py', 'module': 'os'}], count=7)
    install(monkeypatch, 'unused', result)
    answer = DepsAdapter(str(tmp_path)).get_structure()
    assert answer['analysis']['components']['unused']['completeness'] == 'failed'
    assert len(answer['unused']) == answer['analysis']['findings']['unused'] == 1


@pytest.mark.parametrize('state', ['incomplete', 'failed'])
@pytest.mark.parametrize('cycles', [0, 2])
def test_text_does_not_claim_clean_circular_analysis_without_proof(tmp_path, monkeypatch, state, cycles):
    from reveal.rendering.adapters.deps import deps_text
    result = child('circular')
    result.update(cycles=[['a.py', 'b.py']] * cycles, count=cycles)
    if state == 'incomplete':
        result['metadata']['files_failed_count'] = 1
    else:
        result['error'] = 'cycle analysis unavailable'
    install(monkeypatch, 'circular', result)
    text = deps_text(DepsAdapter(str(tmp_path)).get_structure())
    assert 'no circular deps' not in text
    assert 'nothing to check for cycles' not in text
    assert ('circular dependency analysis incomplete' if state == 'incomplete' else
            'circular dependency analysis unavailable') in text
    if cycles:
        assert '2 circular dep(s)' in text


def test_real_recovered_zero_imports_does_not_claim_nothing_to_check(tmp_path):
    from reveal.rendering.adapters.deps import deps_text
    (tmp_path/'a.py').write_text('def broken(\n', encoding='utf-8')
    text = deps_text(DepsAdapter(str(tmp_path)).get_structure())
    assert 'nothing to check for cycles' not in text
    assert 'circular dependency analysis incomplete' in text


def test_clean_and_skipped_circular_text_remain_unchanged(tmp_path, monkeypatch):
    from reveal.rendering.adapters.deps import deps_text
    install(monkeypatch)
    clean = deps_text(DepsAdapter(str(tmp_path)).get_structure())
    skipped = deps_text(DepsAdapter(str(tmp_path), 'no_circular=true').get_structure())
    assert 'nothing to check for cycles' in clean
    assert 'circular deps not checked (--no-circular)' in skipped
    assert 'analysis incomplete' not in clean + skipped


@pytest.mark.parametrize('component,field', [('circular', 'cycles'), ('unused', 'unused')])
@pytest.mark.parametrize('value', [None, 7])
def test_unusable_finding_array_is_unknown_not_zero(tmp_path, monkeypatch, component, field, value):
    result = child(component)
    result[field] = value
    install(monkeypatch, component, result)
    answer = DepsAdapter(str(tmp_path)).get_structure()
    assert answer['analysis']['findings'][component] is None


@pytest.mark.parametrize('component,field', [('circular', 'cycles'), ('unused', 'unused')])
@pytest.mark.parametrize('count', [0, 7])
def test_usable_finding_array_has_exact_count_despite_invalid_count_proof(tmp_path, monkeypatch, component, field, count):
    result = child(component)
    result[field] = [['a.py', 'b.py']] if component == 'circular' else [{'file': 'a.py', 'module': 'os'}]
    result['count'] = count
    install(monkeypatch, component, result)
    answer = DepsAdapter(str(tmp_path)).get_structure()
    assert answer['analysis']['findings'][component] == 1
    assert len(answer['circular']['cycles'] if component == 'circular' else answer['unused']) == 1


def test_valid_empty_findings_are_measured_zero(tmp_path, monkeypatch):
    install(monkeypatch)
    answer = DepsAdapter(str(tmp_path)).get_structure()
    assert answer['analysis']['findings'] == {'circular': 0, 'unused': 0}


@pytest.mark.parametrize('state', ['incomplete', 'failed'])
@pytest.mark.parametrize('findings', [0, 2])
def test_unused_only_missing_evidence_is_visible_in_text(tmp_path, monkeypatch, state, findings):
    from reveal.rendering.adapters.deps import deps_text
    result = child('unused')
    result.update(unused=[{'file': 'a.py', 'module': 'os'}] * findings, count=findings)
    if state == 'incomplete':
        result['metadata'].update(files_failed_count=1, files_lost_count=1)
    else:
        result['error'] = 'unused analysis inaccessible'
    install(monkeypatch, 'unused', result)
    answer = DepsAdapter(str(tmp_path)).get_structure()
    text = deps_text(answer)
    assert ('unused import analysis incomplete' if state == 'incomplete' else
            'unused import analysis unavailable') in text
    assert answer['analysis']['findings']['unused'] == findings
    if findings:
        assert '2 unused import(s)' in text


@pytest.mark.parametrize('state', ['incomplete', 'failed'])
def test_base_only_missing_evidence_is_visible_in_text(tmp_path, monkeypatch, state):
    from reveal.rendering.adapters.deps import deps_text
    result = child('base')
    if state == 'incomplete':
        result['metadata']['files_failed_count'] = 1
    else:
        result['error'] = 'base inventory inaccessible'
    install(monkeypatch, 'base', result)
    text = deps_text(DepsAdapter(str(tmp_path)).get_structure())
    assert ('base import analysis incomplete' if state == 'incomplete' else
            'base import analysis unavailable') in text


def test_clean_and_explicitly_skipped_components_have_no_failure_label(tmp_path, monkeypatch):
    from reveal.rendering.adapters.deps import deps_text
    install(monkeypatch)
    clean = deps_text(DepsAdapter(str(tmp_path)).get_structure())
    install(monkeypatch, 'unused', OSError('must not run'))
    skipped = deps_text(DepsAdapter(str(tmp_path), 'no_unused=true').get_structure())
    assert 'unused imports not checked (--no-unused)' in skipped
    assert 'analysis incomplete' not in clean + skipped
    assert 'analysis unavailable' not in clean + skipped
