"""BACK-1480: tree-sitter surface scanners disclose a partly-recovered parse.

tree-sitter never fails, it guesses. A scanner walking the recovered tree used to
report entries out of ERROR regions as if they were code (WordPress formatting.php:
10 fabricated `subprocess` hits from backticks in a docblock) and never said the
file was degraded -- only the Python scanner reported UNPARSED_KEY.
"""

import importlib
from io import StringIO
from unittest.mock import patch

import pytest

from reveal.adapters.ast.surface_matrix import RECOVERED_KEY
from reveal.cli.commands.surface import _SURFACE_SCANNERS, _render_report, _scan_surface

# One unbalanced-brace snippet per tree-sitter language: parses with error recovery.
_BROKEN = {
    'typescript': ('a.ts', 'function f( {\n  const x = 1;\n}}}\n'),
    'java': ('A.java', 'class A { void f( { } }}}\n'),
    'csharp': ('A.cs', 'class A { void F( { } }}}\n'),
    'php': ('a.php', "<?php\nfunction a() { return 1; }\n}}} `ls -la`;\ngetenv('X');\n"),
    'swift': ('a.swift', 'func f( {\n let x = 1\n}}}\n'),
    'kotlin': ('a.kt', 'fun f( {\n val x = 1\n}}}\n'),
    'ruby': ('a.rb', 'def f(\n  x = 1\nend end end\n'),
    'go': ('a.go', 'package main\nfunc f( {\n}}}\n'),
    'rust': ('a.rs', 'fn f( {\n let x = 1;\n}}}\n'),
    'cpp': ('a.cpp', 'int f( {\n int x = 1;\n}}}\n'),
}
_CLEAN = {
    'typescript': ('a.ts', 'function f() { return 1; }\n'),
    'java': ('A.java', 'class A { void f() { } }\n'),
    'csharp': ('A.cs', 'class A { void F() { } }\n'),
    'php': ('a.php', "<?php\nfunction a() { return getenv('X'); }\n"),
    'swift': ('a.swift', 'func f() { let x = 1 }\n'),
    'kotlin': ('a.kt', 'fun f() { val x = 1 }\n'),
    'ruby': ('a.rb', 'def f\n  1\nend\n'),
    'go': ('a.go', 'package main\nfunc f() {}\n'),
    'rust': ('a.rs', 'fn f() { let x = 1; }\n'),
    'cpp': ('a.cpp', 'int f() { return 1; }\n'),
}
_TS_SCANNERS = [s for s in _SURFACE_SCANNERS if s.language != 'python']


def _scan(spec, path):
    return getattr(importlib.import_module(spec.module), spec.func)(str(path))


def test_every_tree_sitter_language_is_covered_here():
    assert {s.language for s in _TS_SCANNERS} == set(_BROKEN) == set(_CLEAN)


@pytest.mark.parametrize('spec', _TS_SCANNERS, ids=lambda s: s.language)
def test_recovered_parse_is_disclosed(spec, tmp_path):
    name, source = _BROKEN[spec.language]
    f = tmp_path / name
    f.write_text(source, encoding='utf-8')
    assert _scan(spec, f)[RECOVERED_KEY] == [str(f)]


@pytest.mark.parametrize('spec', _TS_SCANNERS, ids=lambda s: s.language)
def test_clean_parse_is_not_flagged(spec, tmp_path):
    name, source = _CLEAN[spec.language]
    f = tmp_path / name
    f.write_text(source, encoding='utf-8')
    assert RECOVERED_KEY not in _scan(spec, f)


def test_php_entry_in_error_region_is_tagged_and_clean_entry_is_not(tmp_path):
    spec = next(s for s in _TS_SCANNERS if s.language == 'php')
    f = tmp_path / 'a.php'
    f.write_text(_BROKEN['php'][1], encoding='utf-8')
    result = _scan(spec, f)
    shell = result['subprocess'][0]
    env = result['env'][0]
    assert (shell['line'], shell.get('in_error_region')) == (3, True)
    assert (env['line'], env.get('in_error_region')) == (4, None)


def test_scan_report_names_recovered_files_and_counts_tagged_entries(tmp_path):
    (tmp_path / 'a.php').write_text(_BROKEN['php'][1], encoding='utf-8')
    (tmp_path / 'ok.php').write_text(_CLEAN['php'][1], encoding='utf-8')
    report = _scan_surface(tmp_path)

    assert report['recovered_files'] == ['a.php']
    assert report['unparsed_files'] == []
    note = next(n for n in report['_meta']['known_limits'] if 'error recovery' in n)
    assert note.startswith('1 file(s) parsed with error recovery; 1 entries lie in a recovered region')
    # The entries stay in the totals -- disclosed, not dropped (most in-region C++ hits are real).
    assert len(report['surfaces']['subprocess']) == 1
    assert RECOVERED_KEY not in report['surfaces']


def test_text_report_marks_the_entry_and_warns(tmp_path):
    (tmp_path / 'a.php').write_text(_BROKEN['php'][1], encoding='utf-8')
    report = _scan_surface(tmp_path)
    with patch('sys.stdout', new_callable=StringIO) as out:
        _render_report(report)
    text = out.getvalue()
    assert '1 file(s) parsed with error recovery' in text
    assert 'a.php:3  [parse-recovered]' in text
    assert 'a.php:4  [parse-recovered]' not in text


def test_clean_scan_reports_no_recovered_files(tmp_path):
    (tmp_path / 'ok.php').write_text(_CLEAN['php'][1], encoding='utf-8')
    report = _scan_surface(tmp_path)
    assert report['recovered_files'] == []
    assert not any('error recovery' in n for n in report['_meta']['known_limits'])
