"""BACK-1113: outlines say so when they cover only a small part of a code file."""

import json

import pytest

from reveal.analyzers.php import PhpAnalyzer
from reveal.analyzers.python import PythonAnalyzer
from reveal.display.coverage import format_coverage_warning, outline_coverage
from reveal.display.structure import _handle_standard_output, _render_json_output


def _script(header, n):
    return header + [f'$v{i} = helper({i});' for i in range(n)]


def test_script_with_one_helper_is_partial():
    lines = ['<?php', 'function helper($a) { return $a; }'] + [f'$v{i} = 1;' for i in range(200)]
    structure = {'functions': [{'line': 2, 'line_end': 2, 'name': 'helper'}]}
    cov = outline_coverage(structure, lines)
    assert cov['uncovered_lines'] == 200          # `<?php` tag is not counted
    assert cov['first_uncovered_line'] == 3
    assert cov['covered_lines'] == 1


def test_class_heavy_file_with_module_glue_is_not_flagged():
    lines = ['class A:'] + ['    x = 1'] * 300 + ['a = A()'] * 20
    structure = {'classes': [{'line': 1, 'line_end': 301, 'name': 'A'}]}
    assert outline_coverage(structure, lines) is None


def test_small_file_is_not_flagged():
    lines = ['def f(): pass'] + ['x = 1'] * 30
    assert outline_coverage({'functions': [{'line': 1, 'line_end': 1, 'name': 'f'}]}, lines) is None


def test_non_code_structures_are_never_assessed():
    lines = ['# t'] + ['text'] * 400
    assert outline_coverage({'headings': [{'line': 1, 'name': 't'}]}, lines) is None
    # a mixed shape (unknown category alongside functions) is also skipped
    assert outline_coverage({'functions': [{'line': 1, 'line_end': 1}], 'rows': [1]}, lines) is None
    assert outline_coverage({}, lines) is None


def test_imports_count_as_covered():
    lines = ['import a'] * 100 + ['x = 1'] * 120 + ['def f(): pass']
    structure = {'imports': [{'line': n} for n in range(1, 101)],
                 'functions': [{'line': 221, 'line_end': 221, 'name': 'f'}]}
    cov = outline_coverage(structure, lines)
    assert cov['uncovered_lines'] == 120 and cov['first_uncovered_line'] == 101


def test_warning_text_never_rounds_up_to_100_percent():
    cov = {'code_lines': 1000, 'covered_lines': 1, 'uncovered_lines': 999,
           'covered_fraction': 0.001, 'first_uncovered_line': 2}
    first, second = format_coverage_warning(cov, 'x.php')
    assert '(99%)' in first and 'first at line 2' in first and ':2-<end>' in second


@pytest.fixture
def php_script(tmp_path):
    path = tmp_path / 'script.php'
    path.write_text('\n'.join(['<?php', 'function helper($a) { return $a + 1; }']
                              + [f'$v{i} = helper({i});' for i in range(200)]) + '\n')
    return PhpAnalyzer(str(path))


def test_text_output_warns_for_procedural_php(php_script, capsys):
    _handle_standard_output(php_script, php_script.get_structure(), 'text', False, '')
    out = capsys.readouterr().out
    assert 'Functions (1)' in out and 'Partial outline' in out


def test_json_output_carries_coverage_meta(php_script, capsys):
    _render_json_output(php_script, php_script.get_structure())
    meta = json.loads(capsys.readouterr().out)['meta']
    assert meta['coverage']['uncovered_lines'] == 200


def test_fully_declared_python_has_no_warning(tmp_path, capsys):
    path = tmp_path / 'ok.py'
    path.write_text('\n'.join(f'def f{i}():\n    return {i}\n' for i in range(120)))
    analyzer = PythonAnalyzer(str(path))
    _handle_standard_output(analyzer, analyzer.get_structure(), 'text', False, '')
    assert 'Partial outline' not in capsys.readouterr().out


# ── parse-recovery notice (upstream grammar gaps, BACK-742/756/703/768) ─────

def test_outline_notice_when_the_parse_recovered_around_errors(tmp_path, capsys):
    path = tmp_path / 'bad.py'
    path.write_text('def ok():\n    return 1\n\ndef broken(:\n    pass\n\ndef after():\n    return 2\n')
    analyzer = PythonAnalyzer(str(path))
    structure = analyzer.get_structure()
    assert structure.get('_has_errors')
    _handle_standard_output(analyzer, structure, 'text', False, '')
    assert 'Parse recovered' in capsys.readouterr().out


def test_json_meta_flags_parse_recovery(tmp_path, capsys):
    path = tmp_path / 'bad.py'
    path.write_text('def broken(:\n    pass\n')
    analyzer = PythonAnalyzer(str(path))
    _render_json_output(analyzer, analyzer.get_structure())
    assert json.loads(capsys.readouterr().out)['meta']['parse_recovered'] is True


def test_clean_file_has_no_parse_notice(tmp_path, capsys):
    path = tmp_path / 'ok.py'
    path.write_text('def ok():\n    return 1\n')
    analyzer = PythonAnalyzer(str(path))
    _handle_standard_output(analyzer, analyzer.get_structure(), 'text', False, '')
    assert 'Parse recovered' not in capsys.readouterr().out


def test_go_trailing_missing_token_is_not_reported_as_recovery(tmp_path):
    """A valid Go file ending in an interface parses with a lone trailing
    `(MISSING "source_file_token1")` -- a grammar quirk, not a lost parse."""
    from reveal.analyzers.go import GoAnalyzer
    path = tmp_path / 'm.go'
    path.write_text('package p\n\ntype M interface {\n\tTimes() map[string]*int\n}\n')
    assert GoAnalyzer(str(path))._has_recovery_artifacts() is False


def test_real_error_alongside_go_still_reports_recovery(tmp_path):
    from reveal.analyzers.go import GoAnalyzer
    path = tmp_path / 'bad.go'
    path.write_text('package p\n\nfunc f( {\n')
    assert GoAnalyzer(str(path))._has_recovery_artifacts() is True
