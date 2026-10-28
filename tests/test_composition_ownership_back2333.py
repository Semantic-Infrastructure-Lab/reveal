"""Composing a reused answer owns only its envelope, never its analysis payload."""

from copy import deepcopy

import pytest

from reveal.adapters.ast import AstAdapter
from reveal.adapters.base import ResourceAdapter
from reveal.utils.results import ResultBuilder, note_truncation, truncations_of


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


def test_clean_composition_retains_answer_and_consuming_contract():
    answer = {'source': 'relative', 'items': [1, 2]}
    parent = Parent()
    assert parent.compose_answer(AstAdapter, 'relative', lambda: answer) == answer
    assert parent.composed_meta() is None


@pytest.mark.parametrize('component', ['base', 'circular', 'unused'])
def test_deps_projects_cuts_before_diagnostic_snapshot(tmp_path, monkeypatch, component):
    from reveal.adapters import deps

    payload = {'base': {'files': {}}, 'circular': {'cycles': [], 'count': 0},
               'unused': {'unused': [], 'count': 0}}[component]
    child = ResultBuilder.create('imports', '.', data=payload)
    child['metadata'] = {'files_failed_count': 2, 'files_lost_count': 2,
                         'files_failed': ['lost.py'], 'files_lost': ['lost.py']}
    note_truncation(child, 'metadata.files_failed', 1, 2, 'auto_cap')
    original = deepcopy(child)
    monkeypatch.setattr(deps, '_build', lambda *args: child)
    monkeypatch.setattr(deps, '_view', lambda *args: child)
    adapter = deps.DepsAdapter(str(tmp_path))
    getattr(deps, f'_run_{component}')(adapter, tmp_path)
    warning, = truncations_of({'meta': adapter.composed_meta()})
    assert warning['field'] == f'analysis.components.{component}.diagnostics.files_failed'
    assert child == original
    parent.record_composed_error('AstAdapter', 'relative', ValueError('required child failed'))
    meta = parent.composed_meta()
    assert meta['confidence'] == 0.0
    assert meta['errors'][0]['code'] == 'E_COMPOSE'
    assert parent.composed_meta() is None
