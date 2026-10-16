"""A file whose structure analysis raises is disclosed, not dropped (BACK-1856).

``analyze_file`` used to print to stderr and return None, so ast://, architecture://
and overview:// complexity lists omitted the file with nothing in the result's meta.
"""
from pathlib import Path

import pytest

from reveal.adapters.ast import AstAdapter, analysis
from reveal.adapters.imports import ImportsAdapter, _extract_one_file


@pytest.fixture
def tree(tmp_path, monkeypatch):
    (tmp_path / 'ok.py').write_text('def a():\n    return 1\n')
    (tmp_path / 'bad.py').write_text('def b():\n    return 2\n')
    real = analysis.create_element_dict

    def boom(file_path, *args, **kwargs):
        if file_path.endswith('bad.py'):
            raise ValueError('synthetic analyzer bug')
        return real(file_path, *args, **kwargs)

    monkeypatch.setattr(analysis, 'create_element_dict', boom)
    return tmp_path


def _analysis_failed(warnings):
    return [w for w in warnings if w.get('type') == 'analysis_failed']


def test_outcome_separates_failure_from_no_analyzer(tree):
    structure, failure = analysis.analyze_file_outcome(str(tree / 'bad.py'))
    assert structure is None and failure == 'ValueError: synthetic analyzer bug'
    (tree / 'notes.unknownext').write_text('x')
    assert analysis.analyze_file_outcome(str(tree / 'notes.unknownext')) == (None, None)
    structure, failure = analysis.analyze_file_outcome(str(tree / 'ok.py'))
    assert structure and failure is None


def test_collect_structures_records_skipped(tree):
    structures = analysis.collect_structures(str(tree))
    assert [Path(s['file']).name for s in structures] == ['ok.py']
    assert [(Path(f).name, c) for f, c in structures.skipped] == [
        ('bad.py', 'ValueError: synthetic analyzer bug')]


def test_ast_query_warns_about_the_skipped_file(tree):
    result = AstAdapter(str(tree), 'complexity>0').get_structure()
    (warning,) = _analysis_failed(result['meta']['warnings'])
    assert warning['count'] == 1
    assert warning['files'][0].endswith('bad.py')
    assert 'ValueError' in warning['message']


def test_clean_tree_has_no_analysis_warning(tmp_path):
    (tmp_path / 'ok.py').write_text('def a():\n    return 1\n')
    result = AstAdapter(str(tmp_path), 'complexity>0').get_structure()
    assert not _analysis_failed(result['meta']['warnings'])


def test_imports_graph_discloses_the_skipped_file(tree):
    importer = ImportsAdapter(str(tree))
    importer._build_graph(tree, collect_structures=True)
    assert [Path(s['file']).name for s in importer._structures] == ['ok.py']
    (warning,) = _analysis_failed(importer.integrity_warnings(tree))
    assert warning['files'] == ['bad.py']


def test_extract_one_file_returns_the_failure(tree):
    *_, structure, _extraction, failure = _extract_one_file(str(tree / 'bad.py'), True)
    assert structure is None and 'synthetic analyzer bug' in failure
