"""Analysis boundaries isolate diagnostics even when construction is interrupted."""

import pytest

from reveal.adapters.architecture import ArchitectureAdapter
from reveal.adapters.ast import AstAdapter
from reveal.adapters.base import ResourceAdapter
from reveal.utils.results import ResultBuilder


class Parent(ResourceAdapter):
    def get_structure(self, **kwargs):
        return {}


def test_exception_before_architecture_finalization_does_not_contaminate_reuse(tmp_path, monkeypatch):
    from reveal.adapters import architecture

    (tmp_path / 'module.py').write_text('def healthy():\n    return 1\n', encoding='utf-8')
    adapter = ArchitectureAdapter(str(tmp_path), 'no_imports=true')

    def fail_risks(*args):
        raise ValueError('risk construction failed')

    with monkeypatch.context() as patch:
        patch.setattr(AstAdapter, 'get_structure', lambda *a, **kw: ResultBuilder.create_error(
            'ast_query', str(tmp_path), 'required child failed'))
        patch.setattr(architecture, '_compute_risks', fail_risks)
        with pytest.raises(ValueError, match='risk construction failed'):
            adapter.get_structure()
    reused = adapter.get_structure()
    fresh = ArchitectureAdapter(str(tmp_path), 'no_imports=true').get_structure()
    assert reused == fresh


def test_nested_runs_restore_outer_diagnostics_and_clean_up_unconsumed_failure():
    parent = Parent()
    with parent.composition_run():
        parent.fold_meta({'warnings': [{'type': 'outer', 'message': 'outer warning'}],
                          'confidence': 0.75})
        with pytest.raises(ValueError, match='inner failed'):
            with parent.composition_run():
                parent.record_composed_error('inner', 'resource', OSError('input lost'))
                raise ValueError('inner failed')
        outer = parent.composed_meta()
        assert outer['confidence'] == 0.75
        assert outer['warnings'] == [{'type': 'outer', 'message': 'outer warning'}]
        assert outer['errors'] == []
    assert parent.composed_meta() is None


def test_repeated_unconsumed_runs_do_not_retain_diagnostics():
    parent = Parent()
    for index in range(100):
        with parent.composition_run():
            parent.fold_meta({'warnings': [{'type': 'iteration', 'message': str(index)}]})
    assert parent.composed_meta() is None


def test_nested_completed_answer_can_be_folded_once_into_outer_run():
    parent = Parent()
    with parent.composition_run():
        with parent.composition_run():
            parent.record_composed_error('required', 'resource', OSError('input lost'))
            inner = parent.composed_meta()
        parent.fold_meta(inner)
        outer = parent.composed_meta()
        assert len(outer['errors']) == 1
        assert outer['confidence'] == 0.0
        assert parent.composed_meta() is None
    assert parent.composed_meta() is None


def test_xlsx_analyzer_warning_does_not_leak_after_banner_exception(tmp_path, monkeypatch):
    import zipfile
    from reveal.adapters.xlsx import XlsxAdapter

    path = tmp_path / 'book.xlsx'
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('xl/workbook.xml', '<workbook/>')
    adapter = XlsxAdapter(str(path))

    def fail_banner():
        raise ValueError('banner construction failed')

    with monkeypatch.context() as patch:
        patch.setattr(adapter.analyzer, 'get_structure', lambda: {
            'sheets': [], 'meta': {'warnings': [{'type': 'sheet_parse_failed',
                                               'message': 'previous workbook warning'}]}})
        patch.setattr(adapter, '_build_powerpivot_banner', fail_banner)
        with pytest.raises(ValueError, match='banner construction failed'):
            adapter.get_structure()
    assert adapter.get_structure() == XlsxAdapter(str(path)).get_structure()
