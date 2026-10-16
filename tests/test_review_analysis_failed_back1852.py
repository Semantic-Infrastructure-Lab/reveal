"""`reveal review` and tree-sitter outlines say when an analysis step lost its results (BACK-1852)."""
from pathlib import Path

import pytest

from reveal.adapters.ast import analysis
from reveal.cli.commands import review


def test_analysis_failed_names_step_target_and_cause():
    w = review._analysis_failed('complexity', Path('a.py'), ValueError('x'))
    assert w['type'] == 'analysis_failed' and w['message'] == 'complexity: a.py: ValueError: x'
    assert review._analysis_failed('hotspots', None, KeyError('k'))['message'].startswith('hotspots: KeyError')


def test_per_target_complexity_failure_is_a_warning(tmp_path, monkeypatch):
    good, bad = tmp_path / 'good.py', tmp_path / 'bad.py'
    good.write_text('def f():\n    return 1\n')
    bad.write_text('def g():\n    return 1\n')
    from reveal.adapters.ast import adapter as ast_adapter
    real_cls = ast_adapter.AstAdapter

    class Boom(real_cls):
        def get_structure(self, *a, **k):
            if str(self.path).endswith('bad.py'):
                raise RuntimeError('boom')
            return super().get_structure(*a, **k)

    monkeypatch.setattr(ast_adapter, 'AstAdapter', Boom)
    warnings = []
    review._run_complexity(None, files=[good, bad], warnings=warnings)
    assert [w['type'] for w in warnings] == ['analysis_failed']
    assert 'bad.py' in warnings[0]['message'] and 'RuntimeError: boom' in warnings[0]['message']


def test_ast_skipped_file_reaches_review_caveats(tmp_path, monkeypatch):
    (tmp_path / 'a.py').write_text('def f():\n    return 1\n')
    def boom(file_path, *args, **kwargs):
        raise ValueError('synthetic')

    monkeypatch.setattr(analysis, 'create_element_dict', boom)
    warnings = []
    review._run_complexity(tmp_path, warnings=warnings)
    assert any(w['type'] == 'analysis_failed' and 'a.py' in w['message'] for w in warnings)


def test_complexity_failure_makes_review_incomplete():
    report = {'meta': {'warnings': [{'type': 'analysis_failed', 'message': 'complexity: x'}]}}
    assert review._lost_analysis(report)
    assert review._review_outcome([], [], analysis_incomplete=True) == ('incomplete', 3)


def test_clean_complexity_run_adds_no_warning(tmp_path):
    (tmp_path / 'a.py').write_text('def f():\n    return 1\n')
    warnings = []
    review._run_complexity(tmp_path, warnings=warnings)
    assert warnings == []


@pytest.fixture
def go_file(tmp_path):
    f = tmp_path / 'ts.go'
    f.write_text('package main\nimport "fmt"\nfunc main() { fmt.Println("x") }\n')
    return f


def test_outline_discloses_a_failed_imports_extractor(go_file, monkeypatch):
    from reveal.analyzers.imports import base
    from reveal.registry import get_analyzer
    real = base.get_extractor

    def failing(path):
        ex = real(path)
        if ex is not None:
            def raiser(_p):
                raise RuntimeError('boom')
            ex.extract_imports = raiser
        return ex

    monkeypatch.setattr(base, 'get_extractor', failing)
    analyzer = get_analyzer(str(go_file))(str(go_file))
    structure = analyzer.get_structure()
    assert structure['_imports_failed'] == 'RuntimeError: boom'
    from reveal.display.structure import _imports_failed_warnings
    (w,) = _imports_failed_warnings(structure)
    assert w['type'] == 'imports_failed' and 'RuntimeError: boom' in w['message']


def test_outline_without_failure_has_no_imports_warning(go_file):
    from reveal.registry import get_analyzer
    from reveal.display.structure import _imports_failed_warnings
    structure = get_analyzer(str(go_file))(str(go_file)).get_structure()
    assert '_imports_failed' not in structure and _imports_failed_warnings(structure) == []
