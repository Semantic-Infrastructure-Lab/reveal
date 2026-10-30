"""Retained AST composition belongs to comparison; ordinary aliases do no AST work."""
import pytest
from reveal.adapters.architecture import ArchitectureAdapter
from reveal.adapters.ast import AstAdapter
from reveal.diff.architecture_diff import _run_complex_functions, _snapshot
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


def test_comparison_ast_cuts_and_warnings_retain_the_shared_owner(project):
    first, second = AstAdapter(str(project)), AstAdapter(str(project))
    ranked = _run_complex_functions(first, project, 2)
    expected = _run_complex_functions(second, project, 2)
    metadata = first.composed_meta()
    assert ranked == expected and len(ranked) == 2
    assert [(row['name'], row['complexity']) for row in ranked] == [
        ('function_0', 13), ('function_1', 13)]
    assert metadata == second.composed_meta()
    cut, = truncations_of({'meta': metadata})
    assert (cut['field'], cut['shown'], cut['total']) == ('complex_functions', 2, 6)
    assert 'raise ?top=N' in cut['message']


@pytest.mark.parametrize('kind', ['returned', 'meta_errors', 'confidence', 'raised'])
def test_comparison_retains_child_failure_metadata(project, monkeypatch, kind):
    original = AstAdapter.get_structure
    def answer(self, *args, **kwargs):
        if kind == 'raised':
            raise OSError('required AST input unreadable')
        if kind == 'returned':
            return ResultBuilder.create_error('ast_query', str(project), 'required AST input unreadable')
        result = original(self, *args, **kwargs)
        if kind == 'meta_errors':
            result['meta']['errors'].append({'code': 'required_input_failed', 'message': 'AST input unreadable'})
        result['meta']['confidence'] = 0.25
        return result
    monkeypatch.setattr(AstAdapter, 'get_structure', answer)
    report = _snapshot(project, 2)
    metadata = report['meta']
    if kind in ('returned', 'raised'):
        assert any('required AST input unreadable' in error['message'] for error in metadata['errors'])
        assert metadata['confidence'] == 0.0
    elif kind == 'meta_errors':
        assert any(error['code'] == 'required_input_failed' for error in metadata['errors'])
        assert metadata['confidence'] == 0.25
    else:
        assert not metadata['errors'] and metadata['confidence'] == 0.25
    assert report['completeness']['complexity'] == ('complete' if kind == 'confidence' else 'failed')


@pytest.mark.parametrize('query', ['', 'no_imports=true'])
def test_ordinary_alias_never_requests_retired_ast_assessment(project, monkeypatch, query):
    def forbidden(*args, **kwargs):
        pytest.fail('ordinary alias requested AST assessment')
    monkeypatch.setattr(AstAdapter, 'get_structure', forbidden)
    result = ArchitectureAdapter(str(project), query).get_structure()
    assert result['type'] == 'overview'
    assert result['map_status'] == ('not_requested' if query else 'complete')
    assert not result.get('meta', {}).get('errors')
