"""surface:// language x category coverage matrix (BACK-1332)."""

import ast
from pathlib import Path

import pytest

from reveal.adapters import surface as surface_adapter
from reveal.adapters.ast import surface_matrix as sm
from reveal.adapters.ast import surface_rules
from reveal.adapters.surface import _SURFACE_SCANNERS, _render_report, _scan_surface

_AST_DIR = Path(surface_adapter.__file__).parent / 'ast'


def _emitted_categories(module: str) -> set:
    """Categories a hand-coded scanner can put entries under, read from its source.

    Three spellings exist: `surfaces['cat']`, an import-taxonomy tuple `(TABLE, 'cat')`,
    and `category, kind = 'cat', ...` (PHP).
    """
    tree = ast.parse((_AST_DIR / f'{module}.py').read_text())
    found = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name)
                and node.value.id == 'surfaces' and isinstance(node.slice, ast.Constant)):
            found.add(node.slice.value)
        elif (isinstance(node, ast.Tuple) and len(node.elts) == 2
                and isinstance(node.elts[1], ast.Constant)):
            found.add(node.elts[1].value)
        elif isinstance(node, ast.Assign) and any(
                'category' in {n.id for n in ast.walk(t) if isinstance(n, ast.Name)}
                for t in node.targets):
            found.update(c.value for c in ast.walk(node.value) if isinstance(c, ast.Constant))
    return found & set(sm.CATEGORIES)


@pytest.mark.parametrize('lang', sorted(sm.SCANNER_MODULES))
def test_hand_coded_declaration_matches_the_scanner_source(lang):
    """The declared cells are exactly what the scanner's code can emit (no drift either way)."""
    assert _emitted_categories(sm.SCANNER_MODULES[lang]) == set(sm._HAND_CODED[lang])


@pytest.mark.parametrize('lang', sorted(sm.SCANNER_MODULES))
def test_a_category_is_never_both_rule_driven_and_hand_coded(lang):
    """A migrated category must leave _HAND_CODED in the same change (else the cell lies)."""
    both = set(surface_rules.rule_categories(lang)) & set(sm._HAND_CODED[lang])
    assert not both, f'{lang}: {sorted(both)} are rule-driven but still declared hand-coded'


def test_every_registered_scanner_owns_one_matrix_column():
    registered = {spec.language: spec.module.rsplit('.', 1)[-1] for spec in _SURFACE_SCANNERS}
    assert registered == sm.SCANNER_MODULES


def test_rule_table_cells_are_reported_as_rules():
    assert sm.cell_status('go', 'subprocess') == sm.RULES
    assert sm.cell_status('typescript', 'subprocess') == sm.SCANNER
    assert sm.cell_status('ruby', 'fs') == sm.NOT_IMPLEMENTED


def test_matrix_is_total_over_languages_and_categories():
    matrix = sm.coverage_matrix(['go', 'ruby'])
    assert set(matrix['cells']) == {'go', 'ruby'}
    for row in matrix['cells'].values():
        assert tuple(row) == sm.CATEGORIES


def test_not_applicable_is_honoured_and_removes_the_gap(monkeypatch):
    monkeypatch.setitem(sm._NOT_APPLICABLE, 'ruby', frozenset({'fs'}))
    assert sm.cell_status('ruby', 'fs') == sm.NOT_APPLICABLE
    assert 'fs' not in sm.coverage_matrix(['ruby'])['not_implemented']


def test_unknown_language_is_entirely_not_implemented():
    assert set(sm.language_row('cobol').values()) == {sm.NOT_IMPLEMENTED}


def _scan(tmp_path, files, **kw):
    for name, code in files.items():
        (tmp_path / name).write_text(code)
    return _scan_surface(tmp_path, **kw)


def test_scan_reports_the_gap_instead_of_a_silent_zero(tmp_path):
    report = _scan(tmp_path, {'a.rb': 'x = 1\n'})
    assert report['surfaces']['fs'] == []
    assert report['matrix']['cells']['ruby']['fs'] == sm.NOT_IMPLEMENTED
    assert report['matrix']['not_implemented']['fs'] == ['ruby']


def test_matrix_covers_only_languages_the_scan_met(tmp_path):
    report = _scan(tmp_path, {'a.py': 'x = 1\n'})
    assert set(report['matrix']['cells']) == {'python'}
    assert report['matrix']['not_implemented'] == {}


def test_type_filter_narrows_the_matrix_to_that_category(tmp_path):
    report = _scan(tmp_path, {'a.rb': 'x = 1\n', 'b.py': 'x = 1\n'}, type_filter='fs')
    assert report['matrix']['not_implemented'] == {'fs': ['ruby']}
    assert all(set(row) == {'fs'} for row in report['matrix']['cells'].values())


def test_text_report_names_the_languages_with_no_detector(tmp_path, capsys):
    _render_report(_scan(tmp_path, {'a.rb': 'x = 1\n', 'b.swift': 'let x = 1\n'}))
    out = capsys.readouterr().out
    assert 'Not implemented for scanned languages' in out
    assert 'fs: Swift, Ruby' in out or 'fs: Ruby, Swift' in out
    assert 'No external surfaces detected' in out


def test_text_report_is_quiet_when_nothing_is_missing(tmp_path, capsys):
    _render_report(_scan(tmp_path, {'a.py': 'import os\nos.system("x")\n'}))
    assert 'Not implemented' not in capsys.readouterr().out
