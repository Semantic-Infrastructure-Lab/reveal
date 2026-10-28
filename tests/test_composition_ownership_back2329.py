"""Composing a reused answer owns only its envelope, never its analysis payload."""

from copy import deepcopy

import pytest

from reveal.adapters.ast import AstAdapter
from reveal.adapters.architecture import ArchitectureAdapter
from reveal.adapters.base import ResourceAdapter
from reveal.utils.results import ResultBuilder, truncations_of


class Parent(ResourceAdapter):
    def get_structure(self, **kwargs):
        return {}


@pytest.fixture
def ast_answer(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'module.py').write_text(
        ''.join(f'def function_{i}():\n    return {i}\n\n' for i in range(4)),
        encoding='utf-8',
    )
    answer = AstAdapter(str(tmp_path), 'limit=1').get_structure()
    assert truncations_of(answer)
    return answer


def test_reused_ast_answer_keeps_original_source_and_cuts(ast_answer):
    original = deepcopy(ast_answer)
    parent = Parent()
    composed = parent.compose_answer(
        AstAdapter, '.', lambda: ast_answer,
        cut_as=('complex_functions', 'raise ?top=N'),
    )
    assert composed['source'] == '.'
    assert truncations_of(composed)[0]['field'] == 'complex_functions'
    assert ast_answer == original
    assert composed['results'] is ast_answer['results']
    sibling = Parent()
    sibling.compose_answer(AstAdapter, '.', lambda: ast_answer)
    assert truncations_of({'meta': sibling.composed_meta()})[0]['field'] == 'results'


def test_warning_filter_does_not_hide_reused_child_diagnostics(ast_answer):
    warning = {'type': 'analysis_incomplete', 'message': 'child input missing'}
    ast_answer['meta']['warnings'].append(warning)
    original = deepcopy(ast_answer)
    first = Parent()
    first.compose_answer(AstAdapter, '.', lambda: ast_answer,
                         omit_warnings=lambda w: w.get('type') == 'analysis_incomplete')
    assert warning not in first.composed_meta()['warnings']
    second = Parent()
    second.compose_answer(AstAdapter, '.', lambda: ast_answer)
    assert warning in second.composed_meta()['warnings']
    assert ast_answer == original


def test_folded_diagnostics_are_a_snapshot_but_payload_is_not_copied():
    warning = {'type': 'analysis_incomplete', 'message': 'original'}
    error = {'code': 'E_INPUT', 'message': 'original error'}
    parent = Parent()
    parent.fold_meta({'warnings': [warning], 'errors': [error], 'confidence': 0.25})
    warning['message'] = 'changed child'
    error['message'] = 'changed child error'
    meta = parent.composed_meta()
    assert meta['warnings'][0]['message'] == 'original'
    assert meta['errors'][0]['message'] == 'original error'
    assert meta['confidence'] == 0.25


def test_exception_before_architecture_finalization_does_not_contaminate_reuse(tmp_path, monkeypatch):
    from reveal.adapters import architecture

    (tmp_path / 'module.py').write_text('def healthy():\n    return 1\n', encoding='utf-8')
    adapter = ArchitectureAdapter(str(tmp_path), 'no_imports=true')
    with monkeypatch.context() as patch:
        patch.setattr(AstAdapter, 'get_structure', lambda *a, **kw: ResultBuilder.create_error(
            'ast_query', str(tmp_path), 'required child failed'))
        patch.setattr(architecture, '_compute_risks', lambda *a: (_ for _ in ()).throw(
            ValueError('risk construction failed')))
        with pytest.raises(ValueError, match='risk construction failed'):
            adapter.get_structure()
    reused = adapter.get_structure()
    fresh = ArchitectureAdapter(str(tmp_path), 'no_imports=true').get_structure()
    assert reused == fresh


def test_clean_composition_retains_answer_and_consuming_contract():
    answer = {'source': 'relative', 'items': [1, 2]}
    parent = Parent()
    assert parent.compose_answer(AstAdapter, 'relative', lambda: answer) == answer
    assert parent.composed_meta() is None
    parent.record_composed_error('AstAdapter', 'relative', ValueError('required child failed'))
    meta = parent.composed_meta()
    assert meta['confidence'] == 0.0
    assert meta['errors'][0]['code'] == 'E_COMPOSE'
    assert parent.composed_meta() is None
