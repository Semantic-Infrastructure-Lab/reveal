"""Shared-walk architecture retains the AST owner's trust diagnostics."""

import pytest

from dataclasses import replace
from reveal.analyzers.imports import service as import_service

from reveal.adapters.architecture import (
    ArchitectureAdapter, _run_combined_analysis, _run_complex_functions,
)
from reveal.adapters.ast import AstAdapter
from reveal.adapters.ast.analysis import StructureList
from reveal.adapters.imports import ImportsAdapter
from reveal.utils.results import ResultBuilder, truncations_of


@pytest.fixture
def project(tmp_path):
    source = ''.join(
        f'def function_{i}(value):\n'
        + ''.join(f'    if value == {j}:\n        return {j}\n' for j in range(12))
        + '    return -1\n\n'
        for i in range(6)
    )
    (tmp_path / 'module.py').write_text(source, encoding='utf-8')
    return tmp_path


def test_real_ast_cuts_and_warnings_match_standalone(project):
    combined = ArchitectureAdapter(str(project))
    ranked, _ = _run_combined_analysis(combined, project, 2)
    shared_meta = combined.composed_meta()
    standalone = ArchitectureAdapter(str(project))
    expected = _run_complex_functions(standalone, project, 2)
    expected_meta = standalone.composed_meta()
    assert ranked == expected
    assert len(ranked) == 2
    assert shared_meta == expected_meta
    cut = truncations_of({'meta': shared_meta})[0]
    assert cut['field'] == 'complex_functions'
    assert cut['shown'] == 2 and cut['total'] == 6
    assert 'raise ?top=N' in cut['message']


@pytest.mark.parametrize('kind', ['returned', 'meta_errors', 'confidence', 'raised'])
def test_child_failure_metadata_survives(project, monkeypatch, kind):
    original = AstAdapter.get_structure

    def answer(self, *args, **kwargs):
        if kind == 'raised':
            raise OSError('required AST input unreadable')
        if kind == 'returned':
            return ResultBuilder.create_error(
                'ast_query', str(project), 'required AST input unreadable')
        result = original(self, *args, **kwargs)
        if kind == 'meta_errors':
            result['meta']['errors'].append(
                {'code': 'required_input_failed', 'message': 'AST input unreadable'})
        result['meta']['confidence'] = 0.25
        return result

    monkeypatch.setattr(AstAdapter, 'get_structure', answer)
    adapter = ArchitectureAdapter(str(project))
    report = adapter.get_structure()
    meta = report['meta']
    if kind in ('returned', 'raised'):
        assert any('required AST input unreadable' in e['message'] for e in meta['errors'])
        assert meta['confidence'] == 0.0
    elif kind == 'meta_errors':
        assert {'code': 'required_input_failed', 'message': 'AST input unreadable'} in meta['errors']
        assert meta['confidence'] == 0.25
    else:
        assert not meta['errors']
        assert meta['confidence'] == 0.25
    # Diagnostics are consumed once rather than contaminating later calls.
    assert adapter.composed_meta() is None


@pytest.mark.parametrize('kind', ['analysis_failed', 'parse_recovered', 'harmless'])
def test_real_ast_warning_producers_reach_architecture(project, monkeypatch, kind):
    build = import_service.analyze
    structures_seen = []

    def shared(scope, **kwargs):
        built = build(scope, **kwargs)
        assert kwargs['structure_reader'] is not None
        structures = StructureList(built.structures)
        if kind == 'analysis_failed':
            structures.skipped.append((str(project / 'lost.py'), 'OSError: unreadable'))
        elif kind == 'parse_recovered':
            structures[0]['parse_recovered'] = True
        structures_seen.append(structures)
        return replace(built, structures=structures)

    original = AstAdapter.get_structure

    def answer(self, structures=None, **kwargs):
        assert structures is structures_seen[-1]
        return original(self, structures=structures, **kwargs)

    def no_second_walk(self):
        pytest.fail('shared structures must bypass AST collection')

    monkeypatch.setattr(import_service, 'analyze', shared)
    monkeypatch.setattr(AstAdapter, 'get_structure', answer)
    monkeypatch.setattr(AstAdapter, '_collect_structures', no_second_walk)
    report = ArchitectureAdapter(str(project)).get_structure()
    warnings = report['meta']['warnings']
    expected = 'complexity_is_unweighted' if kind == 'harmless' else kind
    assert any(w.get('type') == expected for w in warnings)
    assert not report['meta']['errors']
    assert len(structures_seen) == 1


def test_no_imports_composition_retains_same_child_error(project, monkeypatch):
    def error(self, **kwargs):
        return ResultBuilder.create_error('ast_query', str(project), 'AST failed')

    monkeypatch.setattr(AstAdapter, 'get_structure', error)
    result = ArchitectureAdapter(str(project), 'no_imports=true').get_structure()
    assert result['no_imports'] is True
    assert not result['facts']['entry_points']
    assert result['meta']['confidence'] == 0.0
    assert any('AST failed' in e['message'] for e in result['meta']['errors'])


def test_returned_child_ranking_and_source_are_preserved(project, monkeypatch):
    original = AstAdapter.get_structure
    answers = []

    def answer(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        answers.append(result)
        return result

    monkeypatch.setattr(AstAdapter, 'get_structure', answer)
    adapter = ArchitectureAdapter(str(project))
    _run_combined_analysis(adapter, project, 2)
    assert answers[0]['source'] == project.as_posix()
    assert adapter.composed_meta()['warnings']
    assert len(answers[0]['results']) == 2
    assert all(row['complexity'] == 13 for row in answers[0]['results'])


def test_no_imports_not_applicable_child_remains_non_error(project, monkeypatch):
    def declined(self, **kwargs):
        return ResultBuilder.create(
            'ast_query', str(project), applicable=False, reason='no applicable structures',
            warnings=[{'type': 'not_applicable', 'code': 'not_applicable', 'message': 'no applicable structures'}])

    monkeypatch.setattr(AstAdapter, 'get_structure', declined)
    result = ArchitectureAdapter(str(project), 'no_imports=true').get_structure()
    assert result['no_imports'] is True
    assert not result['meta'].get('errors')
    assert any(w.get('code') == 'not_applicable' for w in result['meta']['warnings'])
